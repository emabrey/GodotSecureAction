#!/usr/bin/env python3
"""
test_reverse_engineering.py
---------------------------
Runs gdsdecomp's recover_project CLI against an exported Godot PCK and
asserts that the integration test secret string cannot be recovered from
the output.

gdsdecomp is the most capable known Godot reverse-engineering tool. If it
cannot extract the canary value embedded in main.gd, the Godot Secure
encryption is considered to be working correctly.

Usage:
    python test_reverse_engineering.py \\
        --pck   <path/to/exported.pck> \\
        --tool  <path/to/gdre_tools_dir> \\
        --secret <canary_string>

Exit codes:
    0 — secret not found in any recovered output (PASS)
    1 — secret found in recovered output or tool invocation error (FAIL)
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile

# Windows consoles default to a legacy codepage (e.g. cp1252) which cannot
# encode the ✓/✗ characters used in test output. Force UTF-8 with replacement
# so the script never crashes with UnicodeEncodeError on any platform.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def find_tool(tool_dir: str) -> str:
    """Locate the gdre_tools or recover_project executable."""
    patterns = [
        os.path.join(tool_dir, "**", "gdre_tools"),
        os.path.join(tool_dir, "**", "gdre_tools.x86_64"),
        os.path.join(tool_dir, "**", "gdre_tools.exe"),
        os.path.join(tool_dir, "**", "recover_project"),
        os.path.join(tool_dir, "**", "recover_project.exe"),
        os.path.join(tool_dir, "gdre_tools"),
        os.path.join(tool_dir, "gdre_tools.exe"),
        os.path.join(tool_dir, "recover_project"),
        os.path.join(tool_dir, "recover_project.exe"),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        # .exe files are executable on Windows regardless of os.access
        executables = [m for m in matches if os.access(m, os.X_OK) or m.endswith(".exe")]
        if executables:
            return executables[0]

    print(f"✗  No executable found in '{tool_dir}'.")
    print(f"   Searched: {patterns}")
    sys.exit(1)


def secret_in_dir(output_dir: str, secret: str) -> str | None:
    """Return the first file path containing the secret, or None."""
    for root, _dirs, files in os.walk(output_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    if secret in fh.read():
                        return fpath
            except OSError:
                pass
    return None


def run(pck_path: str, tool_dir: str, secret: str) -> int:
    tool = find_tool(tool_dir)
    print(f"  Tool      : {tool}")
    print(f"  PCK       : {pck_path}")
    print(f"  Secret    : {secret!r}")

    with tempfile.TemporaryDirectory(prefix="gdre_out_") as output_dir:
        cmd = [tool, "--headless", "--recover", pck_path,
               "--output-dir", output_dir]
        print(f"\nRunning: {' '.join(cmd)}\n")

        try:
            # Explicit UTF-8 decoding: text=True alone uses the locale encoding
            # (cp1252 on Windows), which raises UnicodeDecodeError on arbitrary
            # tool output. errors="replace" guarantees decoding never crashes.
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            print("✗  gdsdecomp timed out after 180 seconds.")
            return 1
        except FileNotFoundError as exc:
            print(f"✗  Could not launch tool: {exc}")
            return 1

        stdout_snippet = result.stdout[:1000]
        stderr_snippet = result.stderr[:1000]

        print(f"Exit code : {result.returncode}")
        if stdout_snippet:
            print(f"stdout    :\n{stdout_snippet}")
        if stderr_snippet:
            print(f"stderr    :\n{stderr_snippet}")

        # Check stdout / stderr for the secret.
        if secret in result.stdout or secret in result.stderr:
            print(f"\n✗  FAIL — Secret found in gdsdecomp output!")
            return 1

        # Check every recovered file for the secret.
        hit = secret_in_dir(output_dir, secret)
        if hit:
            print(f"\n✗  FAIL — Secret found in recovered file: {hit}")
            return 1

        if result.returncode != 0:
            print(
                f"\n✓  PASS — gdsdecomp exited {result.returncode} and "
                f"could not recover the secret."
            )
        else:
            print(
                f"\n✓  PASS — gdsdecomp exited 0 but the secret string "
                f"does not appear in any recovered output. "
                f"Encryption is intact."
            )

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assert that gdsdecomp cannot recover the integration test secret."
    )
    parser.add_argument("--pck",    required=True, help="Path to the exported PCK file.")
    parser.add_argument("--tool",   required=True, help="Directory containing the gdre_tools binary.")
    parser.add_argument("--secret", required=True, help="Canary string that must not appear in recovered output.")
    args = parser.parse_args()
    sys.exit(run(args.pck, args.tool, args.secret))
