# Experiment 04 — post-alive CL dependency queue probe

**Implemented offline; not device-tested.** Current firmware boot requires
the reset-safe RAM-loader fix `aa8df8a460` or later. The old `a070663751`
arm path hard-locked at a18 in experiment 03 Run 2. Run only after the fixed
experiment 03 reports a firmware-owned type-0 event. This experiment
tests firmware queue progress with one pre-satisfied dependency command;
it does not execute CDM, PDS or USC code and does not establish G3 shader
execution. The probe was introduced at `a070663751`; current source and
reset-safe boot sequencing are in the round-6 head on `a9/gpu`.

**Verified host protocol:** channel pointer ring, tag-4 dependency records,
global CL notification type 2 and R0+0xb00 kick 0x12 are recovered from
AGXG5P. Addresses/layouts: [submission-g5p.md](../submission-g5p.md).
**Inferred experiment:** a satisfied dependency with a zero context pointer
and channel identity zero can be consumed without a subsequent compute
object. That composition has not been captured from a working Apple
channel. The independent `work_experiment` gate defaults false.

## Exact orchestrator commands

Do not run these from a research agent. First use the default
[experiment 03 runner](03-boot-meta.md#one-upload-runner-round-5).
Inspect its summary; proceed only for `alive=1 failed=0`. Keep that boot's
allocated/mapped firmware objects. The runner removes its lock on success;
it refuses a second boot attempt on the same maps.

Enable only the additional work gate, upload the single-stage helper,
and stage CPU/DMA memory:

*(Device/host command block omitted; it targets the private workspace.)*

The helper's default preflight revalidates the CPU-only image and retains
already-staged bytes; it does not repeat map/arm or alter existing coherent
firmware backing.
**Expected:** `work_ready=1 work_submitted=0 work_complete=0`; private
channel META address `c0254000`, slots=16, channel consumer/producer 0/0,
stamp=1, command words (captured state words omitted).
Workspace is 1 KiB at shared+0x54000, inside an already-mapped 16 KiB page;
no additional coherent or CMA allocation is required.

Publish exactly one entry and kick:

*(Device/host command block omitted; it targets the private workspace.)*

**Expected:** `CL publish type=2 sequence=0 slot=...; W R0+00b00=00000012`;
`work_submitted=1`.
The global CL ring must be empty before submission. Its target is the
previous producer+1 modulo 256, usually 1 on a fresh firmware boot.
Private channel producer becomes 1; no slot is overwritten/reused.
R1+0x1000 is read and must already indicate active GPC state 1. This probe
does not guess a firmware power-restart sequence if it is asleep.

Observe bounded completion and capture cached status:

*(Device/host command block omitted; it targets the private workspace.)*

**Expected success:** within three seconds, global consumer equals target,
private channel consumer/producer=1/1, slots=16, stamp=1, no fault event,
`work_complete=1 failed=0`, and `firmware dependency only, no GPU dispatch`.
A global consumer advance alone does not pass. The unchanged stamp is an
input to this satisfied dependency; it is not a shader's output fence.

**Optional combined fresh-boot run:** only after G2 is independently
repeatable, boot with all three explicit gates
`a9_gpu_diag.enable=1 a9_gpu_diag.boot_experiment=1 a9_gpu_diag.work_experiment=1`.
Upload/run the default runner once, then on a separate fresh boot the
orchestrator may upload it without execution using its own transfer method,
or use the following single upload command (the environment assignment is
inside the uploaded script):

*(Device/host command block omitted; it targets the private workspace.)*

This retains the runner's first-failure stop, deadlines and compact summary.
The default runner never enables or submits work automatically.

## Failure shapes and bounds

- **Permission / missing alive:** stop. Check gates and G2's raw event;
  enabling work never substitutes for an alive event.
- **Prepare error:** preserve result. The kernel checks the workspace fits
  one mapped page and lies beyond the recovered used span. No GPU write is
  performed by prepare; do not override a rejected layout.
- **Nonempty global ring / inactive Fender:** no producer/kick is written.
  Record `queues`, cached `registers` and log. Do not bypass the guard or
  force clocks. Determine whether background firmware work or power policy
  needs to be implemented first.
- **Global consumer moves, channel does not:** transport reached the
  scheduler, but the private channel/state/dependency composition was not
  accepted or is waiting. Preserve all indices/command words; do not infer
  completion from a kick or IRQ.
- **Neither consumer moves:** preserve raw GPC status, producers and kick
  log. Possible notification/kick/power/coherency mismatch; do not retry
  into the same slot.
- **Event type 4, 7 or 8 / corrupt index / changed stamp:** failure latches;
  all 11 raw event words are logged, fault entry remains unconsumed, and
  later hardware work is blocked. Preserve backing until reboot.
- **Three-second timeout:** kernel returns an error and latches failure;
  `queues` and `registers` are CPU/cached snapshots with trylock. Reboot
  before another attempt; there is no implemented recovery or safe reuse.
- **Stalled MMIO:** software deadlines cannot abort a nonreturning bus
  transaction. The combined runner stops waiting for its writer, provided
  the scheduler/console remain alive; a whole-SoC lock still needs reboot.

**Next gate after success:** recover/validate the nonzero context object,
the remaining compute work/microsequence fields, the execution-base B
contract and actual stamp retirement, then submit the userspace agent's
captured terminate/compute stream with expected buffer bytes. This probe
deliberately provides no public DRM submission UAPI.
