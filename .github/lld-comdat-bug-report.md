# LLVM bug report — full-LTO COFF codegen: report_fatal_error on associative COMDAT whose leader was dropped/renamed

Target tracker: <https://github.com/llvm/llvm-project/issues> (subprojects: LTO, CodeGen, COFF).

---

**Title:** [LTO][CodeGen][COFF] `report_fatal_error` "Associative COMDAT symbol '…' does not exist" in `getComdatGVForCOFF` when full LTO drops/renames the comdat leader of a `thread_local` template static

### Summary

Linking with **full LTO** on `x86_64-pc-windows-msvc` (`clang-cl` + `lld-link`)
aborts inside the LTO backend's COFF codegen:

```
LLVM ERROR: Associative COMDAT symbol '?tls_data@?$SafeBinaryMutex@$00@@0UTLSData@1@A' does not exist.
PLEASE submit a bug report to https://github.com/llvm/llvm-project/issues/ and include the crash backtrace.
```

The symbol demangles to `SafeBinaryMutex<1>::tls_data` — a `thread_local static`
data member of a class template (from Godot's `core/os/mutex.h`). The build links
cleanly **without** LTO; the crash only appears with `lto=full`.

### Minimal reproducer

The crash is in COFF codegen, so it reproduces directly from a few lines of IR —
**no LTO, no linker, no source build.** The only requirement is a global in a
comdat whose named leader `GlobalValue` is absent (the in-module state full LTO
produces — see below):

```llvm
; missing.ll
target triple = "x86_64-pc-windows-msvc"

$missing_leader = comdat any
@assoc = global i32 0, comdat($missing_leader)   ; member; there is no @missing_leader leader
```

```
clang --target=x86_64-pc-windows-msvc -c missing.ll
```

```
fatal error: error in backend: Associative COMDAT symbol 'missing_leader' does not exist.
clang: error: clang frontend command failed with exit code 70
```

Confirmed on **clang 20.1.8** (`x86_64-pc-windows-msvc`). It crashes identically
**with and without** `-Xclang -disable-llvm-verifier` — i.e. the IR verifier
*accepts* the leaderless comdat, so the malformed module reaches the backend,
which `report_fatal_error`s instead of diagnosing it.

### Root cause

The message comes from `getComdatGVForCOFF` in
`llvm/lib/CodeGen/TargetLoweringObjectFileImpl.cpp` (verified on `release/20.x`):

```cpp
static const GlobalValue *getComdatGVForCOFF(const GlobalValue *GV) {
  const Comdat *C = GV->getComdat();
  assert(C && "expected GV to have a Comdat!");

  StringRef ComdatGVName = C->getName();
  const GlobalValue *ComdatGV = GV->getParent()->getNamedValue(ComdatGVName);
  if (!ComdatGV)
    report_fatal_error("Associative COMDAT symbol '" + ComdatGVName +
                       "' does not exist.");
  ...
}
```

This enforces a COFF invariant: **a comdat's name must match an existing
`GlobalValue` in the module** (the comdat "leader/key"). When lowering a global
`GV` whose comdat leader is *another* symbol, COFF emits `GV`'s section as
`IMAGE_COMDAT_SELECT_ASSOCIATIVE`, associated to that leader. If
`M.getNamedValue(C->getName())` returns null — i.e. the leader no longer exists —
codegen `report_fatal_error`s.

So at the point of the crash there is a surviving global still carrying the comdat
`?tls_data@?$SafeBinaryMutex@$00@@0UTLSData@1@A` (one of the TLS support globals
COFF associates with the variable — guard/init/`.tls$` data), but the **leader
global `tls_data` itself has been removed or renamed**, leaving a dangling
associative comdat.

That state cannot arise from a single object compile (each TU emits a
self-consistent comdat group), which is why it is **LTO-only and deterministic**:
during LTO the multiple `linkonce_odr` copies of `SafeBinaryMutex<true>::tls_data`
are resolved across modules, and the comdat group is broken — the leader is
dropped/renamed while an associated member is kept. The most likely culprit is a
pass that does not treat the comdat group atomically (e.g. GlobalDCE /
Internalize keeping/removing comdat members independently) or a comdat-renaming
transform that doesn't update associated members — note LLVM already has a
regression test for exactly this class of issue:
`llvm/test/Transforms/LowerTypeTests/cfi-coff-comdat-rename.ll`.

### Suggested fix

Keep the COFF invariant intact across LTO so a leaderless associative comdat is
never handed to codegen:

1. **Atomic comdat groups (preferred):** whichever LTO transform removes or
   renames the leader of a comdat must keep the group consistent — either keep
   the leader `GlobalValue` alive while any associated member survives, drop the
   whole comdat group together, or rename the comdat to a surviving member.
   GlobalDCE/Internalize already have comdat-group logic; this case (a
   `thread_local` template static's COFF-associated support globals) appears to
   slip through it.
2. **Fail earlier / more clearly:** the IR `Verifier` currently does **not**
   reject this module — the minimal reproducer above passes verification (crashes
   with and without `-disable-llvm-verifier`) and only fails in the backend.
   Having the verifier reject a COFF comdat whose name has no corresponding
   `GlobalValue` would turn the backend `report_fatal_error` into a deterministic
   verifier error that pinpoints the producing pass. (Defensive — the real fix is #1.)

Bisecting LTO passes (`-mllvm -print-after-all` / saving the pre-codegen LTO
bitcode and running `llvm-dis`) on the attached reproducer should identify the
exact pass that orphans the leader.

### Trigger / evidence (deterministic, LTO-only)

| build | LTO | result |
|-------|-----|--------|
| Godot + Godot Secure patch | `full` | **crash** — 9/9 across CI re-runs |
| Godot + Godot Secure patch | none | links cleanly |
| vanilla Godot (no patch) | `full` | links cleanly — 3/3 (real LTO: `-flto`, `/LTCG`) |

So the crash needs full LTO **and** a module composition in which the comdat
leader gets dropped — vanilla and patched builds differ only in which symbols are
live, which is exactly what determines whether the leader survives. The backtrace
is byte-identical across runs (same offsets modulo ASLR) — same code path every
time, not memory corruption or a race.

### Reproduction

Deterministic for a **full-LTO link of one specific module**: building Godot
Engine 4.6-stable with `lto=full` and the Godot Secure source patch applied
crashes 9/9, while a **vanilla** Godot 4.6 `lto=full` build links cleanly
(verified real LTO — `-flto` on every TU, `/LTCG` link). Whether the comdat
leader survives LTO depends on symbol liveness, which the patch changes.

A complete, self-contained **lld `--reproduce` archive** (post-front-end LTO
bitcode + libs + the exact `lld-link` response file) from a crashing link is
attached — **extract it and run `lld-link @response.txt` to reproduce with no
source build at all** (this is the recommended reproducer; `llvm-reduce` can
shrink the bitcode further). _Attach: `editor-link.tar`._ `lto=none` links cleanly.

### Environment

- Linker/codegen: `lld-link.exe` bundled with **Visual Studio 2026 Enterprise**
  18.6.11822.322 (component `Microsoft.VisualStudio.Component.VC.Llvm.Clang`
  18.6.11706.339); **clang/lld-link 20.1.8** (`clang version 20.1.8`). Standalone
  LLVM on the same image: 20.1.8.
- Compiler: matching `clang-cl`, target `x86_64-pc-windows-msvc`.
- OS: Windows Server 2025 (10.0.26100), GitHub Actions image
  `windows-2025-vs2026` v`20260608.135.2`.

### Backtrace (unsymbolicated — VS-bundled release lld-link, no PDB)

```
Exception Code: 0xC000001D
 #0  lld-link.exe+0x1b021e6
 #1  lld-link.exe+0x1a3ca62
 #2  lld-link.exe+0x1a33058
 #3  lld-link.exe+0x1b0479e
 #4  lld-link.exe+0x1efc85
 …  (frames #5–#21; identical offsets across runs)
 #22 lld-link.exe+0x1a1d0dc
 #23 KERNEL32.DLL+0x2e8d7   (BaseThreadInitThunk)
 #24 ntdll.dll+0x8c53c      (RtlUserThreadStart)
```
(The fatal error originates in `getComdatGVForCOFF`, reached through the LTO
backend's COFF object emission; a PDB-matched/assert-enabled build can
symbolicate the upper frames.)

### Workaround

Link with `lto=none` (or do not use `use_llvm`/clang-cl for full-LTO release
links on this toolchain).
