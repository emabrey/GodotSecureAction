# Draft LLVM bug report — lld-link LTO associative-COMDAT crash

Target tracker: <https://github.com/llvm/llvm-project/issues> (subproject: lld / COFF, LTO).
Structured per <https://llvm.org/docs/HowToSubmitABug.html>.

Fill in the two TODOs (exact `lld-link --version`, attach the reproduce tarball)
from the `lld-repro.yml` workflow before filing.

---

**Title:** [lld][COFF][LTO] `report_fatal_error` "Associative COMDAT symbol '…tls_data…' does not exist" linking a `thread_local` template static with `/lto` (LLVM 20.1.x, lld-link)

### What happens
`lld-link` aborts via `report_fatal_error` (the internal-error path — `LLVM ERROR:`
+ "PLEASE submit a bug report" + stack dump — *not* a normal `lld-link: error:`)
during a **full-LTO** link:

```
LLVM ERROR: Associative COMDAT symbol '?tls_data@?$SafeBinaryMutex@$00@@0UTLSData@1@A' does not exist.
PLEASE submit a bug report to https://github.com/llvm/llvm-project/issues/ and include the crash backtrace.
```

The symbol demangles to `SafeBinaryMutex<1>::tls_data` — a `thread_local static`
data member of a class template (Godot's `core/os/mutex.h`). Its TLS init/guard
sections are emitted as `IMAGE_COMDAT_SELECT_ASSOCIATIVE`, keyed on that symbol;
during the LTO link lld-link fails to resolve the key.

### Trigger: full LTO (deterministic)
The crash correlates **exactly** with `lto=full` (clang-cl + lld-link full LTO):

| build | LTO | result |
|-------|-----|--------|
| `use_llvm=yes lto=full`  | full | **crash** — observed 9/9 across 3 CI re-runs |
| `use_llvm=yes` (no LTO)  | none | links cleanly — many CI runs, never crashed |

So it is **not** intermittent and **not** cache-related (an earlier "intermittent"
impression came from comparing a full-LTO run against no-LTO runs). The crash
backtrace is byte-identical across runs (same offsets modulo ASLR), i.e. the same
code path every time — ruling out memory corruption. It reproduces with vanilla
Godot, so the Godot Secure patch is not involved.

### Where LLVM was obtained
Not upstream git: the **lld-link bundled with Visual Studio 2026 Enterprise**
(18.6.11822.322; component `Microsoft.VisualStudio.Component.VC.Llvm.Clang`
18.6.11706.339), LLVM ≈ 20.1.x. The same GitHub Actions image also ships
standalone **LLVM 20.1.8**.
`lld-link --version`: _TODO — capture from the lld-repro workflow._

### Environment
- Linker: `lld-link.exe` (VS 2026 bundled, `…\VC\Tools\Llvm\x64\bin\lld-link.exe`)
- Compiler: matching `clang-cl`, target `x86_64-pc-windows-msvc`
- OS: Windows Server 2025 (10.0.26100), GitHub Actions image `windows-2025-vs2026` v`20260608.135.2`
- Invocation: `lld-link @<response-file>` (driven by SCons during a Godot build)

### Reproduction
Vanilla **Godot Engine 4.6-stable**, full LTO:

```
scons platform=windows arch=x86_64 target=editor use_llvm=yes d3d12=yes lto=full
```

Crashes at `Linking Program bin\godot.windows.editor.x86_64.llvm.exe`. The same
command with `lto=none` links successfully.

A complete, self-contained reproducer (the lld `--reproduce` tarball: all
objects/bitcode, libs, and the exact response file) is attached, captured via
`LLD_REPRODUCE` on a crashing run. _TODO: attach `editor-link.tar`._

### Backtrace (unsymbolicated — VS-bundled release lld-link, no PDB)
```
Exception Code: 0xC000001D
 #0  lld-link.exe+0x1b021e6
 #1  lld-link.exe+0x1a3ca62
 #2  lld-link.exe+0x1a33058
 #3  lld-link.exe+0x1b0479e
 #4  lld-link.exe+0x1efc85
 …  (frames #5–#21 in lld-link.exe; identical offsets across runs)
 #22 lld-link.exe+0x1a1d0dc
 #23 KERNEL32.DLL+0x2e8d7   (BaseThreadInitThunk)
 #24 ntdll.dll+0x8c53c      (RtlUserThreadStart)
```

### Suspected area / useful diagnostics
- The failure is specific to the **LTO** link path resolving an
  `IMAGE_COMDAT_SELECT_ASSOCIATIVE` section whose key symbol is a `thread_local`
  template static — likely the COMDAT/symbol bookkeeping after the LTO backend
  regenerates objects from bitcode.
- `/threads:1` result on the captured inputs: _TODO from lld-repro_ (expected not
  to matter, since the trigger is LTO, not threading).
- `llvm-readobj`/`llvm-dis` on the LTO-produced object/bitcode defining
  `SafeBinaryMutex<1>::tls_data` to confirm whether the associative key symbol is
  present after LTO codegen.
- A symbolicated backtrace from a PDB-matched / assert-enabled lld-link.

### Workaround
`lto=none` (or avoiding `use_llvm` for full-LTO release links) links cleanly.
