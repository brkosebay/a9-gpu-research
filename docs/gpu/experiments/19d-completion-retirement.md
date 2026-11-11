# R19d — restore the final helper END and observe real retirement

Parent: `fa850de794e6dc17f5cb723d6bffe4e6591a4f85` (`a9/gpu`).
Head: `f3668bbffad5a7b0b1c53eb3313acbad20165893` (`a9/gpu`).
Apply patch0044, then
patch0045, after0043.
No device access, firmware modification, workspace commit or push by this agent.
The corrected GPU helper still needs an orchestrator device test.
The retirement-mirror check is exported in0045;0044 contains the payload gate and diagnostics.

## Evidence and primary fix

The r19c slot7 diagnostic blob confirms `output+200=12345678` and **all63
other output dwords equal deadbeef**. It also has `4a0=0`, zero MMU faults,
stamp0, channel retired0/scan1/endpoint1/producer1, outstanding G+728=1,
and the expected slot7 selectors. The numerical operation succeeded; the
GPU stream/context-store/firmware retirement did not finish.

Firmware research round15 found a concrete
fixture defect: the USC helper at **B+28000** is copied for only40hex bytes,
but its branch at+2 targets **+40**, where the successful iOS capture has
`00 80` (USC END). The old fixture leaves `00 00` at that target. The full
stream's helper packet at CDM+8c reaches this program through PDS14440 and
DOUTU data14450=`28000/10`. This late helper follows the successful user
shader and is therefore the highest-ranked explanation of the split result.
Hardware causality is still untested.

`make-compute-fixture-r19d.py` retains42hex captured bytes and emits separately
named/hashed files. **Exactly one file byte changes:8051,00→80** (page2+41,
including the16-byte file header). It also regenerates the original compute13
files byte-for-byte for controls. The kernel verifies the selected hash
before allocation/publication; a gate/file mismatch returns-EBADMSG.

| Corrected fixture | SHA256 |
|---|---|
| minimal | `33fa9ae4a390…` |
| full | `3389b8090f96…` |

`compute_helper_end` is false in a plain kernel. R19d wrappers explicitly
set it through `GPU_COMPUTE_HELPER_END` (**default1**), and upload both old
and corrected files. It is latched at prepare, including preinstalled VMs.
The correction persists across retained submissions without rebuilding the
GPU payload or changing slot7, page tables, dependency initialization,
channel identity, event4 wait,4a0 poll, finish33 or stamp identity.

## Completion contract and observations

W258 and W25c are **META CPU pointers into retained shared backing**, not
GPU VAs requiring a different user-context mapping. Finish33 writes
`*(u32 *)W25c=W260` after the event4 wait and4a0.COMPLETE poll. W258 is the later retirement mirror: after the scheduler advances ctl10
and the retire scan advances ctl0, its engine2 callback stores W260 through
W258, then emits type1 with identity0 at bitmap0.bit0. The complete CDM terminate
word already exists at+c4. A host IRQ/event-ring delta cannot produce this
stamp or explain the missing USC END. No host stamp store, event ACK,
forced status bit, context-store request or timeout replay was added.

The wait is **12s by default**, configurable as
`GPU_COMPUTE_WAIT_MS=3000..30000`, latched at prepare. At1s,3s and the final
deadline, before containment, it caches:

- Numerical result and the exact preserved-sentinel count, both stamp
  targets with owned-address validation, W258..284, timestamp queue/stamp
  area, channel controls/ring, and the complete SKU.
- Helper argument/output memory at output+100..2ff, scratch head and tail,
  all submission/event/log control words, all pending44-byte event entries
  and nearby consumed/future entries, including ring wrap.
- Firmware execution-record pointers/cursors and pending masks from owned
  RAM. Private8000a2bc stays explicitly unavailable; external data is not
  represented as a live private-RAM mirror or live META PC.
- Kick/context request/resume/terminate state, MTSb00/b20, event-enableb70, timer160/164,
  event130,4a0.COMPLETE/NEED_RESUME, selector copies and split MMU faults.
  MMIO has an active-wrapper gate and cached progress breadcrumbs.

The first successful job gets a retired snapshot too. The normal failure
dump still contains all eight payload pages and the sparse RAM history.
Read `diagnostic_status` for overflow or a stalled-read breadcrumb; all
three exported diagnostic files are cached readers.

`compute_numerical=1 compute_sentinels=63` is exposed independently of
`compute_complete`. The summary prints **numerical:PASS** even on an
output-correct timeout, with **retirement:NOT_COMPLETE** and a nonzero
overall exit code. Only a matching current stamp, numerical validation,
both firmware stamps (W25c and W258), all five channel indices
(ctl0/10/20/30/40), drained submission rings and cleared G+724/728/72c
allow `compute_complete=1` and a successful repeatable render-node fence.
Stamp-before-retirement now waits instead of returning a premature success.
Faults and timeouts retain the prior reboot/quarantine behavior.

The IRQ storm budget now follows the existing bounded compute event budget,
rather than stopping a legitimate retained run at IRQ257. IRQ/event faults
still latch failure and prevent reuse. No general COMPUTE capability was added.

## Ranked commands

Each line is a **separate fresh integrated r19d boot**, stock DTB, with no
unrelated GPU overrides. Defaults retain slot7, full fixture, dependency1,
policy7, cache3, MMU1/after-cache1, sink1 and ACK0. R19d requires observer194.

1. Correct the proven helper defect, keeping every completion wait:

   *(Device/host command block omitted; it targets the private workspace.)*

2. Same build, original payload control, with the longer diagnostics:

   *(Device/host command block omitted; it targets the private workspace.)*

3. If corrected full still stalls, omit only the two Apple type3 DOUTC
   tasks; keep the other helpers and move the CDM terminate/W pointers to+8c:

   *(Device/host command block omitted; it targets the private workspace.)*

4. Then compare the two user packets with terminate+38, without the helper tail:

   *(Device/host command block omitted; it targets the private workspace.)*

5. Timestamp isolation, keeping event4 and4a0 waits:

   *(Device/host command block omitted; it targets the private workspace.)*

If4a0 becomes COMPLETE but the stamp stays0, use
`GPU_COMPUTE_COMPLETION=2 scripts/gpu/run-compute-host-r19d.sh` on another
fresh boot. This replaces the event4 wait with a zero-mask opcode1 wait;
the real4a0.COMPLETE poll and finish33 remain mandatory. Variant3 combines
this with timestamp removal. Timestamp removal substitutes five zero-mask
wait words per packet, preserving all SKU positions, sequence locations
and the real-0x6c retry backlink. These are independent diagnostic variants,
not firmware-event or completion synthesis. Original behavior is variant0.

All variants can use `GPU_COMPUTE_WAIT_MS=30000`. Device command deadlines,
the render client's timeline deadline and its alarm cover that maximum.
Logs include helper/tail/completion/wait selections in the filename and
are collected under the printed `build/gpu/exp12-r19d-*` prefix.

## Integrated warm-boot compatibility

The same ranked GPU commands run on the integrated kernel containing
`a9/boot`. They check observer194 and writable root-only sysfs parameters,
not `uname`/kernel-tree identity. Both DRM and diagnostic frontends retain
inert defaults. The host log adds `-boot.txt` containing boot_id, cmdline,
uname and the kexec DT marker, alongside the full dmesg with provider status.

For each warm attempt, use a new boot_id and the target boot cmdline's
`apple_pmgr.kexec_gpu_cycle=1` per the boot contract.
The provider's `kexec GFX power cycle complete (actual 0 -> f)` must precede
GPU activation after a faulted/parked previous attempt. The GPU runner sets
its own knobs after boot and does not change this early PMGR parameter.
No old DMA/VM/firmware addresses are carried across kernels. Outer-domain
reset effectiveness remains a device check; this implementation does not
claim a new kernel alone proves the old GPU is reset.

A `git merge-tree --write-tree a9/gpu a9/boot` check is clean; the PMGR boot
hook does not rename/intercept GPU module parameters. This is a source-merge
check plus the GPU build, not a warm-reboot device result. The orchestrator
still builds/stages the complete integration tree.

## Copied-program boundary audit

`scripts/gpu/audit-fixture-r19d.py` checks the actual `compute-layout.h`
anchors, all seven CDM packet pointers and six transitive DOUTU targets
against strict successful iOS capture reads. All six reachable USC programs
retain their complete instruction-aligned END, with known branch targets
landing inside those extents: B+180 and4c0 are182hex bytes each; user22c0
and helpers14040/14280/28000 are42hex bytes each. Twelve copied PDS programs,
including both conditional paths through earlier HALTs, also compare exactly
through their terminal HALT. The only original omission in this closure is
B+28040. The corrected full file equals the one-byte research candidate.

The broad B+180..800 copy also includes **40hex bytes of an unreferenced
code-pool fragment at B+7c0**, with uncopied nonzero capture bytes following
B+800. No fixed W, context-PDS or CDM DOUTU target points there. Its full
extent/semantics are not inferred, and it is unchanged to preserve the exact
one-byte comparison. There is no second reachable truncated program in the
known fixture closure. This is not a general disassembler proof of all USC
semantics. Details are in `build/gpu/fixture-audit-r19d.json`.

## Retained render-node path

On a fresh boot, keep the successful variant's selections and enable repeat:

*(Device/host command block omitted; it targets the private workspace.)*

Only after **retirement:PASS**, on the same boot:

*(Device/host command block omitted; it targets the private workspace.)*

The old monotonic sequence/endpoint wrap, unchanged context/dependency/scratch,
fresh output sentinels and immutable latched variants persist on each repeat.
`GPU_COMPUTE_SERVER=1 GPU_COMPUTE_UAPI=1 GPU_COMPUTE_LIMIT=1048576` also retains
the no-submit warm-server workflow. Numerical success without retirement
does not permit either sysfs or render-node resubmission.

## Offline validation

Run `scripts/gpu/check-round19d.sh`, then
`scripts/build-kernel.sh --tree gpu`. No check accesses the device.
The suite covers the captured branch target/one-byte correction and old/new
hash separation; all six USC/twelve PDS program boundaries; both user slots; all completion/tail combinations and
latched repeat state; production wait/retire ordering, stale stamps,
output-only success, corrupt sentinels, event failures, wrapped/full rings
and foreign stamp pointers under ASan/UBSan. It also runs fake sysfs/SSH,
retained runner/recovery cases, W=1 for both frontends, stock/coherent DTB
comparison, the r19d client compile, strict checkpatch, and r18c regressions.

Validation passed:72 fake-sysfs wrapper cases,19 fake-SSH host cases,
57 runner flow cases, production-helper ASan/UBSan suites, both frontends
with W=1, stock/coherent DTB comparison, r19d client compilation, strict
checkpatch (zero errors/warnings/checks), and the r18c regression suite.
Logs: `build/gpu/check-round19d.log`, `test-mmu-r19d.log` and
`build-round19d.log`. Both exported patches also pass strict checkpatch and a temporary-index
reverse-application reproduces the exact parent tree. The read-only merge
with `a9/boot` is clean. Final full kernel build passed: `build/kernel-gpu/COMMIT` matches the
head above, `DIRTY` is empty,105 DTBs are present and debug info is disabled.
The orchestrator must merge/build this head into the warm-capable integration
tree before staging the next device boot. No device outcome is claimed.
