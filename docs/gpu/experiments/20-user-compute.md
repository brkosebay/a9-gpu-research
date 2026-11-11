# R20 — bounded user-BO compute

Parent: `f3668bbffad5a7b0b1c53eb3313acbad20165893` (r19d).
Head: `87b7d90e76648c4105e644e1f1980788930f3b72` on `a9/gpu`.
Apply 0046
after0045. No device access, integration-tree operation, workspace commit or
push by this implementation agent. Hardware execution of this path remains
untested; offline checks do not qualify a GPU fence.

## Implemented contract

The round14 contract is adopted:
bit15 BOUNDED_COMPUTE and command0f SUBMIT_COMPUTE use its exact80-byte
structure. Existing SUBMIT remains160 bytes. Legacy JOB_COMPUTE stays
EOPNOTSUPP because it cannot bound a stream. The round14 raw client and
private ICD use command0f already; their fallback draft header needs no edit.
The exported header includes the new definitions and
context state3 LIVE.

`a9_gpu_drm.compute_user_experiment` is root-writable and **defaults off**.
Only this gate exposes COMPUTE, VM_LIVE, CONTEXT_LIVE, CODE_BASE_VERIFIED and
BOUNDED_COMPUTE. GET_EXEC_INFO reports common USC/PDS base300000000,
VM scope,34000-byte public window,4000 alignment and32-bit offsets.
These values are identical for every VM, and preserve the base used by the
r19c numerical store. RENDER/PRIME remain absent. The gate enables an
implemented experimental dialect; it does not report a hardware test result.
CREATE_CONTEXT remains HOST_ONLY until DC3 consumption; any accepted-job
error reports LOST. A fault also reports LOST through the existing core latch.

Compute contexts belong to the DRM file and draw from a device-wide locked
slot pool7..255. Slots0..6 are reserved. Never-published contexts release
their slot on destruction. An accepted context keeps its slot until reboot;
there is no idle-slot eviction, resident-VM scheduling or reuse after errors.
The first context on a fresh boot gets7, independent of its DRM handle.

MAP/UNMAP retain the existing GEM backing and16KiB tables. Every changed
PC/PD/PT descriptor uses the r19 generation helper, including exact UNMAP,
parent pruning and allocation-failure rollback. Overlap, partial UNMAP,
reserved firmware/private ranges, offset/length/alignment/overflow errors
are rejected. Identical descriptor writes do not bump a generation. Before
attachment, all tables receive coherent-DMA ordering plus explicit PoC
visibility, then the actual user catalogue PA and packed generation are
published to its slot. DC3 consumes that binding; the r19c post-cache
slot-aware all-level MMU invalidate completes before CL publication.
Once accepted, VM edits/destruction return EBUSY. No live post-attachment
MAP/UNMAP or generation-wrap reuse is offered in this first one-job path.

Submission copies the handle and sync arrays once and resolves owned handles.
The exact first-store dialect requires the five mapped ranges/roles from
round14: READ|EXEC code300000000, READ PDS300030000, READ arguments100048000,
READ CDM10005c000 and READ|WRITE output100000000, each4000 bytes. Bounds,
terminator and all USC/PDS/DMA/argument references are checked by byte
allowlisting, including zero holes. The only accepted shader is the captured
66-byte12345678 first-store. All five BOs must be listed, exactly once;
unknown programs/stream sizes return EOPNOTSUPP, malformed bytes/ranges/roles
EINVAL, absent handles ENOENT and bad user copies EFAULT. More BOs, arbitrary
relocations/constants, links, indirect launches and general SPIR-V are outside
this dialect. CPU writes remain privileged and caller-serialized as in r14.

Binary/timeline input snapshots, exactly one output, at most16 inputs,
duplicate input rejection, same-handle ordering and the shared one-second
queue deadline use the existing syncobj worker. Expired/error inputs suppress
the hardware call. Every rejection precedes output fence replacement and
firmware publication. After acceptance, context→VM→all mappings/GEM/DMA and
DRM references survive handle/fd close, even if dependency wait or preparation
fails. job_id/status remain owned by that file. Copy-out EFAULT/EINTR may
follow acceptance; the clients retain their no-retry behavior.

## Executed data and private helpers

The GPU reads the **user's** code/PDS/arguments and writes the **user's** output
mapping. No CPU path puts12345678 into it. The public CDM's two validated
28-byte packets and its terminator are copied to an immutable private stream;
the r19d helper tail is inserted before that final terminator. All user packet
words and their USC/PDS references are preserved. The original user stream
is rechecked while copying. Other BO content remains caller-serialized;
there is no unprivileged concurrent-writer validation guarantee.

The SHA256-checked `apple/g5p-compute19d-full.bin` supplies only private helper
resources/templates, including the restored final USC END. The fixed shader
copy in that template is never referenced by the user packets. Context
USC/PDS is relocated from B+180..800 to a private B+40180..40800; its two
DOUTU targets become40180/404c0. Its PDS data moves to B+44000, with scratch
low/high/low32(S+20) patches. The W context/resume descriptors follow those
relocations. Private CDM helpers at B+14000/B+28000 retain their original
relative offsets and complete END/HALT extents.

Private scratch is100080000..100087fff, the composed stream1000a0000 and
helper output1000a4000. The helper loader's output+100 and scratch-tail
argument are redirected to the private helper output. No helper initialization
is written into any of the five public BOs. These addresses and the private
code/data pages cannot be MAP targets in a bounded VM. Private mappings and
the borrowed firmware/sink parent entries also bump MMU generations.

The worker uses DC3, cache variant3, MMU variant1 after cache, the actual
allocated slot, initialized dependency state and unchanged r19d event4 wait,
4a0.COMPLETE poll, finish33, W25c and later W258 retirement mirror. Both
stamps, all five channel watermarks, drained submission rings and cleared
G+724/728/72c are mandatory. User GEM output stays device-owned during polls;
diagnostics read private helper output. After retirement, DMA sync returns
GEM ownership to CPU and the whole16KiB output is checked against the r14
expected image, including63 untouched sentinels and untouched outside bytes.
Only then is successful terminal status published before fence signal.

The user firmware wait is6s, leaving room within the unchanged raw client's
12s deadline for the shared1s input/queue bound,3s DC3 wait and bounded
maintenance polls. No timestamp/event/COMPLETE bypass or host stamp synthesis
is added. Any failure marks the context bad, signals its error after terminal
status, retains the entire attachment and refuses another job. Successful
retirement also retains the attachment: ordered unbind/reset is unimplemented.
The accepted-user owner gate blocks subsequent diagnostic command writes,
including park/recover/next, so sysfs cannot reset or rebind its VM.

## Hardware dependency and ranked commands

**Required r19d result:** with slot7, full corrected HELPER_END payload and
baseline completion waits, observe output12345678 plus63 sentinels, **both**
firmware stamps for sequence1, all channel/ring/global retirement checks,
`compute_complete=1` and no MMU/event fault. An output-only pass is insufficient.
This result establishes the retirement recipe used here. It does **not**
prove r20's relocated private helpers, actual GEM output mapping or whole-page
preservation. The raw pass below is that separate qualification; Vulkan then
checks the unchanged private ICD. Keep the new gate off for fixed experiments.

Assuming that r19d result, use these in order on a kernel integrated by the
orchestrator from the head above. No command here builds or touches `integ`.
Raw and Vulkan each require a **separate fresh boot**; inspect/prepare require
an unused device. Warm boots must satisfy the existing PMGR power-cycle
contract.

*(Device/host command block omitted; it targets the private workspace.)*

Inspect enables only the frontend/user gate and reads cached caps/geometry.
Prepare creates/maps/synchronizes/exact-unmaps the five BOs without booting
firmware. Raw/Vulkan reuse the versioned r19d **no-submit** warm-server setup,
then enable the user gate and submit one job. Helpers use the corrected full
file independent of the old fixed fixture's module selections. The wrappers
refuse failed/previous-compute/attach/work boots, pin policy7, disable
preinstallation/readback/boot-VM, clear mock injection and never retry a job.
`serve` warms and enables without submission for manual diagnostics. When
using it, run exactly one raw **or** Vulkan client manually; do not rerun the
host warm-server command on that boot.

The wrappers compile the unchanged round14 raw/probe against r20's installed
header. Vulkan uses the existing hash-checked `round14-device.tar.gz` and its
compatible80-byte draft dialect. Logs live under `build/gpu/r20-STAGE-*`;
the r19d warm-server logs are retained separately. Stop after any fault or
timeout. A new fence alone never authorizes reuse.

## Offline validation

Run `scripts/gpu/check-round20.sh`, then `scripts/build-kernel.sh --tree gpu`.
The first command uses only fake sysfs/SSH and sanitizer binaries; none of
its clients open a real render node. It checks actual production query,
validation, layout, VM allocation/clear/prune/rollback, generation and worker
helpers; all81,920 byte mutations
across the five BOs; owned-handle/copy/role/bounds failure cleanup; inputs,
queue timeout, status-before-fence and bad-context ordering; slots7..255 and
all typed helper relocations. It retains the r19d table/MMU/full-retirement
sanitizer regressions, ARM32/ARM64 ioctl layout checks, round14 transport
doubles, W=1 for both frontends and strict checkpatch. The raw client is
built against the installed new header. Logs are `build/gpu/check-round20.log`
and `build/gpu/build-round20.log`. No offline result is a shader execution.

Validation passed: all checks above,20 fake wrapper cases, both ABI targets,
strict exported-patch checkpatch with zero errors/warnings/checks, and reverse
application reproducing the exact r19d parent tree. The final full GPU-tree
build passed: `build/kernel-gpu/COMMIT` matches the head above, `DIRTY` is
empty,105 DTBs are exported and `CONFIG_DEBUG_INFO_NONE=y`. The workspace
scripts/docs/tests/patch are left for the orchestrator to commit.
