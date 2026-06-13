#!/usr/bin/env python3
"""
check_magic_header.py
---------------------
Verifies the magic header of a Godot PCK file produced by a Godot Secure
patched build.

Usage:
    python check_magic_header.py <path/to/file.pck> [SECURITY_TOKEN]

    SECURITY_TOKEN  Optional 64-character hex security token produced by
                    `godot_secure.py --mode generate`.  When provided the
                    script derives the expected base-tag from the token
                    (same algorithm as godot_secure.py) and verifies the
                    PCK header matches exactly, catching any cross-OS
                    parameter synchronization failures.

Exit codes:
    0 — header matches expected value (or is any non-default value when
        no SECURITY_TOKEN is given)
    1 — header is wrong (default Godot value, or does not match the
        derived base-tag)
    2 — bad arguments or file could not be read
"""

import struct
import sys

# Windows consoles default to a legacy codepage (e.g. cp1252) which cannot
# encode the ✓/✗ characters used in test output. Force UTF-8 with replacement
# so the script never crashes with UnicodeEncodeError on any platform.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_GODOT_MAGIC = 0x43504447  # "GDPC" in little-endian


def tag_to_magic(tag: str) -> int:
    """Convert a 4-char ASCII tag to the little-endian uint32 stored in the PCK."""
    return struct.unpack("<I", tag.encode("ascii"))[0]


def derive_base_tag(token_hex: str) -> str:
    """Derive the base-tag from a 64-char hex security token.

    Mirrors the derive_tags_from_token() function in godot_secure.py:
    bytes 0-3 of the token map to base_tag via chr(ord('A') + (b % 26)).
    """
    token_bytes = bytes.fromhex(token_hex)
    return ''.join(chr(ord('A') + (b % 26)) for b in token_bytes[0:4])


def check(pck_path: str, security_token: str | None) -> int:
    try:
        with open(pck_path, "rb") as fh:
            raw = fh.read(4)
    except OSError as exc:
        print(f"✗  Cannot read '{pck_path}': {exc}")
        return 2

    if len(raw) < 4:
        print(f"✗  '{pck_path}' is too small to contain a magic header.")
        return 2

    actual = struct.unpack("<I", raw)[0]

    if security_token is not None:
        expected_tag = derive_base_tag(security_token)
        expected = tag_to_magic(expected_tag)
        if actual == expected:
            print(
                f"✓  PASS — PCK magic 0x{actual:08X} matches expected "
                f"base-tag '{expected_tag}' (derived from security token)."
            )
            return 0
        elif actual == DEFAULT_GODOT_MAGIC:
            print(
                f"✗  FAIL — PCK has the default Godot magic (0x{actual:08X}). "
                f"The Godot Secure patch was not applied."
            )
        else:
            print(
                f"✗  FAIL — PCK magic 0x{actual:08X} does not match expected "
                f"base-tag '{expected_tag}' (0x{expected:08X}, derived from security token). "
                f"Cross-OS parameter synchronization may have failed."
            )
        return 1

    # No token provided — just verify it is not the default.
    if actual == DEFAULT_GODOT_MAGIC:
        print(
            f"✗  FAIL — PCK has the default Godot magic (0x{actual:08X}). "
            f"The Godot Secure patch was not applied."
        )
        return 1

    print(
        f"✓  PASS — PCK has a custom magic header (0x{actual:08X}). "
        f"Godot Secure patch confirmed."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <pck_file> [SECURITY_TOKEN]")
        sys.exit(2)
    pck = sys.argv[1]
    token = sys.argv[2] if len(sys.argv) == 3 else None
    if token is not None and len(token) != 64:
        print(f"✗  SECURITY_TOKEN must be a 64-character hex string, got {len(token)} chars.")
        sys.exit(2)
    sys.exit(check(pck, token))
