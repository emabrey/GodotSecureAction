# GodotSecureAction

A GitHub Action that builds Godot Engine from source with custom pack encryption. It downloads the Godot Engine C++ source, applies the [Godot Secure](https://github.com/emabrey/Godot-Secure) patch to replace the default pack encryption with a uniquely keyed cipher, then compiles the editor and export templates.

The resulting binaries replace the official Godot editor and export templates and work with any Godot 4.x project.

---

## Verifying with the Estragon example project

[Estragon](https://github.com/emabrey/estragon) is an open-source Godot 4 project template that uses GodotSecureAction for its CI builds. Its PCK encryption key is published intentionally so anyone can verify that the encryption pipeline works end to end.

> **This is the only situation in which publishing a GodotSecure key is appropriate.** Estragon is a template whose sole purpose is to demonstrate the toolchain. For any real game, treat your encryption key as a secret — store it exclusively in a GitHub Actions secret and never commit it to source control. A leaked key lets anyone decrypt your exported PCK files and extract your game's assets and scripts.

### Example key

```
7740b801d92b9a201af5650dad9054f6d52de047992c44df5a633b9c0953a149
```

### How to verify

1. Clone the [Estragon repository](https://github.com/emabrey/estragon) and open it in a Godot editor built with GodotSecureAction (any cipher, any OS build from the published artifacts).

2. In the Godot editor, go to **Project → Export**, select any export preset, open the **Resources** tab, and enter the key above in the **Script encryption key** field.

3. Export the project. The resulting PCK file was encrypted with this key at build time; if your editor binary was built with the same key, the export and re-import will succeed without errors.

4. To confirm the key is actually enforced, repeat the export using a different key — the Godot editor will fail to open the resulting PCK, proving that encryption is active.

### How Estragon stores its key locally

Estragon's `vendored_godot_build.ps1` prompts for the key on first run and stores it as a Windows DPAPI-encrypted blob in `godot.gdkey`. DPAPI ties the blob to the local Windows user account, so the file is useless to anyone who obtains it without access to that account. The plaintext key above is what the build script decrypts from that file at build time and passes to SCons via `SCRIPT_AES256_ENCRYPTION_KEY`.

---

## Quick start

### 1. Add an encryption key secret

Generate a 64-character hex key and store it as a repository secret named `GODOT_ENCRYPTION_KEY`:

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

Go to **Settings → Secrets and variables → Actions → New repository secret** and paste the output.

Set the same key in your Godot project under **Project → Export → Encryption → Script encryption key**.

### 2. Create the build workflow

Create `.github/workflows/build.yml` in your Godot project repository:

```yaml
name: Build Godot Secure

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  # Generate a security token once so every OS build embeds identical values.
  # The token is the single shared secret: the pack magic headers and KDF
  # formula are both derived from it deterministically inside the script, so
  # nothing else needs to be generated or passed separately.
  setup:
    name: Generate shared security parameters
    runs-on: ubuntu-latest
    outputs:
      security-token: ${{ steps.gen.outputs.security-token }}
    steps:
      - name: Download Godot Secure script
        run: |
          curl -fL --retry 5 --retry-delay 10 \
            "https://github.com/emabrey/Godot-Secure/releases/download/v1.4.0/godot_secure.py" \
            -o godot_secure.py
      - name: Generate security token
        id: gen
        run: python3 godot_secure.py --mode generate --non-interactive

  build:
    name: ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    needs: [setup]
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]

    steps:
      - name: Build Godot Secure
        id: godot-secure
        uses: emabrey/GodotSecureAction@v1
        with:
          godot-version:  '4.6-stable'
          algorithm:      aes              # aes · camellia · aria — pick one, use it everywhere
          encryption-key: ${{ secrets.GODOT_ENCRYPTION_KEY }}
          security-token: ${{ needs.setup.outputs.security-token }}

      - name: Upload binaries
        uses: actions/upload-artifact@v7
        with:
          name: godot-secure-${{ steps.godot-secure.outputs.algorithm }}-${{ runner.os }}
          path: godot-source/bin/godot.*
```

Push a commit. The workflow builds the editor and both export templates for Linux, macOS, and Windows in parallel. When all three jobs finish, download the artifact for your platform and use the editor to export your project.

### 3. Pick up your binaries

After the workflow succeeds, go to **Actions → your run → Artifacts** and download the zip for your OS:

```
godot-secure-aes-Linux.zip     → editor + template_debug + template_release (ELF x86_64)
godot-secure-aes-macOS.zip     → editor + template_debug + template_release (arm64)
godot-secure-aes-Windows.zip   → editor + template_debug + template_release (.exe x86_64)
```

Run the editor on your machine to export your project.

---

## Choosing a cipher

Pick one algorithm and use it for **every** OS build. A pack file exported with an AES editor cannot be opened by a Camellia template.

| Cipher | `algorithm` value | Standard | Notes |
|--------|-------------------|----------|-------|
| AES-256 | `aes` | NIST FIPS 197 | Default. Widest adoption; hardware acceleration on most platforms. |
| Camellia-256 | `camellia` | ISO/IEC 18033-3, RFC 3713 | Co-designed by NTT and Mitsubishi; approved for Japanese government use. |
| ARIA-256 | `aria` | Korean KSDS, RFC 5794 | South Korean national standard; mandatory for Korean government systems. |

All three use a 256-bit key and accept the same `SCRIPT_AES256_ENCRYPTION_KEY` environment variable and Godot project key setting.

---

## Inputs

### Godot source

| Input | Default | Description |
|-------|---------|-------------|
| `godot-version` | `4.6-stable` | Godot version tag or branch (e.g. `4.6-stable`, `master`). Downloaded fresh each run. Leave empty only if the source is already in the workspace. |
| `godot-repo` | `godotengine/godot` | GitHub repository to download Godot source from. |
| `godot-source` | `godot-source` | Path where the Godot source root is, or will be downloaded to, relative to the workspace. |

### Godot Secure patch

| Input | Default | Description |
|-------|---------|-------------|
| `godot-secure-repo` | `emabrey/Godot-Secure` | GitHub repository to download the Godot Secure script from. Required — the action fails if this is empty. |
| `godot-secure-tag` | `v1.4.0` | Release tag to download `godot_secure.py` from. |
| `algorithm` | `aes` | Cipher: `aes`, `camellia`, or `aria`. Every platform binary in a distribution must use the same cipher. |
| `encryption-key` | *(empty — random)* | 64-character hex encryption key. Pass your repository secret here. When omitted, a random key is generated and recorded in the log artifact, which is handy for one-off test builds. |
| `security-token` | *(random per job)* | 64-character hex security token (32 bytes). The token is the single shared secret for a build: the pack magic headers and KDF formula are derived from it deterministically via HKDF (RFC 5869) and byte-mapping. **Must be identical across all OS builds.** Generate it once in a `setup` job and pass it via `needs.setup.outputs.security-token`. When omitted, a random token is generated per job, which will cause cross-platform PCK files to fail. |

> **Multi-OS builds:** if `security-token` differs between the Linux, macOS, and Windows jobs, the editor on one platform will be unable to open PCK files exported on another. Always use a `setup` job to generate the token once and pass it to all build jobs; see the examples below.

### Build

| Input | Default | Description |
|-------|---------|-------------|
| `target` | `all` | Build targets: `editor`, `template_debug`, `template_release`, or `all`. |
| `platform` | *(auto)* | SCons platform name. Auto-detected from the runner OS when omitted. |
| `arch` | *(auto)* | Target architecture (e.g. `x86_64`, `arm64`). Auto-detected when omitted. |
| `precision` | `single` | Floating-point precision: `single` or `double`. |
| `lto` | `auto` | Link-time optimisation: `none`, `auto`, or `full`. `auto` skips LTO on editor/debug builds and enables thin LTO on release templates. Use `full` when building release distributions. |
| `extra-scons-args` | *(empty)* | Additional SCons arguments appended to every build invocation. Example: `use_llvm=yes linker=mold`. |
| `scons-cache` | `true` | Cache compiled SCons objects between runs. A warm cache reduces build time substantially on incremental runs. |
| `scons-cache-path` | `.scons-cache` | Directory used for the SCons object cache. |
| `scons-cache-limit` | `1` | Maximum SCons cache size in GB. Godot prunes least-recently-used objects at build end to stay under the limit. `0` means unlimited. |
| `python-version` | `3.x` | Python version used to run SCons and Godot Secure. |

### Platform auto-detection

| Runner OS | SCons platform | Extra SCons args injected automatically |
|-----------|----------------|----------------------------------------|
| Linux | `linuxbsd` | *(none)* |
| macOS | `macos` | `vulkan_sdk_path=<molten-vk prefix>` |
| Windows | `windows` | `d3d12=yes` |

Architecture defaults: `x86_64` on Linux and Windows, auto-detected on macOS (arm64 on Apple Silicon runners).

---

## Outputs

| Output | Description |
|--------|-------------|
| `godot-source-path` | Absolute path to the Godot source tree used for the build. |
| `godot-secure-script` | Absolute path to the downloaded `godot_secure.py`. Empty when `godot-secure-repo` was not set. |
| `editor-path` | Absolute path to the compiled editor binary. Empty if not built. |
| `template-debug-path` | Absolute path to the compiled debug export template. Empty if not built. |
| `template-release-path` | Absolute path to the compiled release export template. Empty if not built. |

---

## More examples

### Trigger on a release tag and produce fully optimised binaries

```yaml
on:
  push:
    tags: ['v*']

jobs:
  setup:
    name: Generate shared security token
    runs-on: ubuntu-latest
    outputs:
      security-token: ${{ steps.gen.outputs.security-token }}
    steps:
      - name: Download Godot Secure script
        run: |
          curl -fL --retry 5 --retry-delay 10 \
            "https://github.com/emabrey/Godot-Secure/releases/download/v1.4.0/godot_secure.py" \
            -o godot_secure.py
      - name: Generate security token
        id: gen
        run: python3 godot_secure.py --mode generate --non-interactive

  build:
    runs-on: ${{ matrix.os }}
    needs: [setup]
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - name: Build Godot Secure
        id: godot-secure
        uses: emabrey/GodotSecureAction@v1
        with:
          godot-version:  '4.6-stable'
          algorithm:      aes
          encryption-key: ${{ secrets.GODOT_ENCRYPTION_KEY }}
          security-token: ${{ needs.setup.outputs.security-token }}
          lto:            full          # maximum optimisation for a release build

      - uses: actions/upload-artifact@v7
        with:
          name: godot-secure-${{ steps.godot-secure.outputs.algorithm }}-${{ runner.os }}
          path: godot-source/bin/godot.*
```

### Run the editor in a downstream step

```yaml
- name: Build Godot Secure
  id: build
  uses: emabrey/GodotSecureAction@v1
  with:
    godot-version:  '4.6-stable'
    algorithm:      aes
    encryption-key: ${{ secrets.GODOT_ENCRYPTION_KEY }}
    target:         editor

- name: Headless version check
  run: |
    "${{ steps.build.outputs.editor-path }}" --headless --version
```

### Pin to a specific Godot Secure release

```yaml
- uses: emabrey/GodotSecureAction@v1
  with:
    godot-version:    '4.6-stable'
    godot-secure-tag: 'v1.4.0'
    algorithm:        camellia
    encryption-key:   ${{ secrets.GODOT_ENCRYPTION_KEY }}
```

### Use a fork of Godot Secure

```yaml
- uses: emabrey/GodotSecureAction@v1
  with:
    godot-version:     '4.6-stable'
    godot-secure-repo: 'my-org/my-godot-secure-fork'
    godot-secure-tag:  'v2.0.0'
    algorithm:         aes
    encryption-key:    ${{ secrets.GODOT_ENCRYPTION_KEY }}
```

### Pass custom SCons arguments

```yaml
- uses: emabrey/GodotSecureAction@v1
  with:
    godot-version:    '4.6-stable'
    algorithm:        aes
    encryption-key:   ${{ secrets.GODOT_ENCRYPTION_KEY }}
    extra-scons-args: 'use_llvm=yes linker=mold'
    target:           editor
```

---

## Provided workflows

This repository ships two workflows used for developing and releasing GodotSecureAction itself. They are not needed for typical project use; the quick start workflow above covers most projects.

### `build.yml` — CI on every push to `main`

Verifies the action works across all cipher and OS combinations after every change. Runs the full 9-job build matrix (3 ciphers × 3 OSes) and four integration tests before producing any artifacts.

### `release.yml` — distributable release zips

Triggered by a tag push (`v*`) or manually from the Actions tab. Produces one zip per cipher containing the editor and both export templates for all three platforms.

| Artifact | Contents |
|----------|----------|
| `godot-{version}-aes-release.zip` | `linux/` `macos/` `windows/` — editor + template_debug + template_release |
| `godot-{version}-camellia-release.zip` | same layout |
| `godot-{version}-aria-release.zip` | same layout |

---

## How it works

1. **Sets up Python** and installs SCons via pip.
2. **Downloads the Godot Engine source** as a tarball from GitHub when `godot-version` is set. Tag URLs are tried first, with branch URLs as a fallback. The source is fetched fresh each run rather than cached, so a moving branch is never served stale and the repo's cache budget stays reserved for compiled objects.
3. **Downloads `godot_secure.py`** from the configured release tag.
4. **Applies the Godot Secure patch** with the chosen `algorithm`. The encryption key is masked in logs and passed exclusively via the `SCRIPT_AES256_ENCRYPTION_KEY` environment variable. All security parameters are derived deterministically from the single security token:
   - **Pack magic headers** — derived via `chr(ord('A') + (byte % 26))` applied to token bytes 0–3 (base-tag) and 4–7 (enc-tag).
   - **KDF formula** — derived via HKDF-SHA256 (RFC 5869) with domain label `godot-secure-kdf-formula-v1`, producing a unique multi-layer bitwise expression mixing the key and token at pack open/write time.
5. **Installs system dependencies** for the runner OS:
   - **Linux** — X11, OpenGL, audio, Wayland, and input headers via `apt-get`
   - **macOS** — MoltenVK (Vulkan) and yasm via Homebrew
   - **Windows** — D3D12 Agility SDK via the Godot-bundled install script
6. **Restores the SCons object cache** to reuse compiled objects from previous runs (when `scons-cache` is `true`).
7. **Runs SCons** for each requested target across all available CPU cores, with `--implicit-cache` to skip unchanged dependency scans across runs.
8. **Locates the compiled binaries** under `bin/` and writes their absolute paths to the step outputs.

---

## Requirements

- Godot 4.x source. Tested against `4.5-stable`, `4.6-stable`, and `master`.
- A repository secret named `GODOT_ENCRYPTION_KEY` containing a 64-character hex string. The same key must be entered in your Godot project's export encryption settings.
- All platform binaries in a project distribution must be built with the same `algorithm`.

---

## Support

GodotSecureAction is free and open-source. If it saves you time, a tip is always appreciated:

<a href="https://ko-fi.com/emabrey" target="_blank">
  <img height="36" src="https://storage.ko-fi.com/cdn/kofi5.png?v=6" border="0" alt="Buy Me a Coffee at ko-fi.com" />
</a>
