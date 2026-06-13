; Minimal reproducer for the COFF codegen crash in getComdatGVForCOFF
; (llvm/lib/CodeGen/TargetLoweringObjectFileImpl.cpp).
;
; A global belongs to a comdat whose *named leader* GlobalValue is absent:
;   $missing_leader = comdat any        ; comdat name "missing_leader"
;   @assoc = ... comdat($missing_leader); member references it
;   ; there is NO @missing_leader global -> the leader was dropped.
;
; At COFF codegen, getComdatGVForCOFF does
;   M->getNamedValue(C->getName())  ->  getNamedValue("missing_leader")  ->  null
; and calls report_fatal_error("Associative COMDAT symbol 'missing_leader'
; does not exist.").
;
; This is exactly the in-module state full LTO produces for Godot's
; thread_local `SafeBinaryMutex<true>::tls_data` (the comdat leader is dropped
; while an associated COFF TLS-support global survives).
;
; Reproduce:
;   llc -mtriple=x86_64-pc-windows-msvc -filetype=obj comdat-leader-missing.ll

target triple = "x86_64-pc-windows-msvc"

$missing_leader = comdat any

; Associated comdat member that outlives its (absent) leader.
@assoc = global i32 0, comdat($missing_leader)
