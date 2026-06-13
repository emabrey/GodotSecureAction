# Draft LLVM bug report — lld-link associative-COMDAT crash

Target tracker: <https://github.com/llvm/llvm-project/issues> (subproject: lld / COFF).
Structured per <https://llvm.org/docs/HowToSubmitABug.html>.

Fill in the two TODOs (exact `lld-link --version`, and attach the reproduce
tarball) from the `lld-repro.yml` workflow before filing.

---

**Title:** [lld][COFF] Non-deterministic `report_fatal_error` "Associative COMDAT symbol '…tls_data…' does not exist" linking a `thread_local` template static (LLVM 20.1.x, lld-link)

### What happened
`lld-link` aborts via `report_fatal_error` (the internal-error path — note
`LLVM ERROR:` + "PLEASE submit a bug report" + stack dump — *not* a normal
`lld-link: error:` diagnostic) while linking an executable:

```
LLVM ERROR: Associative COMDAT symbol '?tls_data@?$SafeBinaryMutex@$00@@0UTLSData@1@A' does not exist.
PLEASE submit a bug report to https://github.com/llvm/llvm-project/issues/ and include the crash backtrace.
```

The symbol demangles to `SafeBinaryMutex<1>::tls_data` — a `thread_local static`
data member of a class template (Godot's `core/os/mutex.h`). Its TLS init/guard
sections are emitted as `IMAGE_COMDAT_SELECT_ASSOCIATIVE`, keyed on that symbol;
lld-link fails to resolve the key.

### Key characteristic: non-deterministic
With identical source, flags, and toolchain the link **crashes on roughly half of
runs and succeeds on the rest** (observed across CI runs of the same commit). The
backtrace bottoms out at `BaseThreadInitThunk`/`RtlUserThreadStart`, consistent
with the fatal error firing during lld-link's parallel input processing —
pointing at a race/ordering bug in associative-COMDAT resolution. See the
`/threads:1` experiment below.

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
Building vanilla **Godot Engine 4.6-stable** from source:

```
scons platform=windows arch=x86_64 target=editor use_llvm=yes d3d12=yes
```

Crash occurs at `Linking Program bin\godot.windows.editor.x86_64.llvm.exe`.

A complete, self-contained reproducer (the lld `--reproduce` tarball: all
objects, libs, and the exact response file) is attached — produced by capturing
`LLD_REPRODUCE` on a crashing run. _TODO: attach `editor-link.tar` from the
lld-repro workflow artifact._

### Backtrace (unsymbolicated — VS-bundled release lld-link, no PDB)
```
Exception Code: 0xC000001D
 #0  lld-link.exe+0x1b021e6
 #1  lld-link.exe+0x1a3ca62
 #2  lld-link.exe+0x1a33058
 #3  lld-link.exe+0x1b0479e
 #4  lld-link.exe+0x1efc85
 …  (frames #5–#21 in lld-link.exe)
 #22 lld-link.exe+0x1a1d0dc
 #23 KERNEL32.DLL+0x2e8d7   (BaseThreadInitThunk)
 #24 ntdll.dll+0x8c53c      (RtlUserThreadStart)
```

### Decisive test / suspected mechanism
- **`/threads:1`**: re-linking the captured reproduce inputs single-threaded — if
  the crash disappears, it localises the bug to parallel input/COMDAT processing
  (and is a usable workaround). _Result: TODO from the lld-repro workflow._
- `llvm-readobj --coff-directives --section-symbols --syms` on the object defining
  `SafeBinaryMutex<1>::tls_data` from a failing build, to check whether the
  associative COMDAT references an existing key symbol (valid input → lld bug) or a
  dangling one (clang-cl object-emission bug).
- A symbolicated backtrace from a PDB-matched / assert-enabled lld-link.
