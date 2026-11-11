# Experiment 11 — empty-VM DC3 attachment

Kernel `a9/gpu` head `9108bbd72d3dfc74e51ab9a230a597b35659833c`, incremental
patch 0026 after round11 head `f7a4087003`. Fresh boot only. Integrate and
build the integrated payload first; `build/kernel-gpu/Image.gz` is GPU-only.
Default boot and both frontends' default-disabled registration are unchanged.

Exp10 CL2 passed dependency scanning with ctl20=1/ctl30=1, ctl0=0 and an
unchanged stamp1. This is the prerequisite transport evidence, not shader
completion. This next experiment isolates the recovered catalogue/DC3 path
before assembling real compute work. No shader, user mapping, execution base,
cache retirement or COMPUTE/VM_LIVE/CONTEXT_LIVE capability is enabled.

The experiment selects the DRM frontend on a fresh boot with diagnostic
frontend disabled, uses dc_variant=7 (meta6c8=0), runs cmd8 and IRQ174 test,
then submits a fenced empty-VM attachment job. Boot catalogue slot0 remains
owned by boot. Slot1 receives the separately allocated empty user root,
with only the existing boot firmware directory shared into its reserved
1GiB window. Slot1's packed version word stays0. The DC entry is
`{3,1,0,0,0}`. There is no slot reuse. The context, VM root and DRM device
are retained until reboot, independently of fence completion and fd close.

## Orchestrator commands

Upload the newly built ARM64 helper and both scripts (no device access by
this agent):

*(Device/host command block omitted; it targets the private workspace.)*

Exact one-line run:

*(Device/host command block omitted; it targets the private workspace.)*

The default render node is `/dev/dri/renderD128`; set `GPU_DIAG_RENDER_NODE`
explicitly if this boot assigns a different node. Do not run CL first: the
attachment probe deliberately refuses an already-prepared CL workspace.
Do not enable the diagnostic frontend on this boot.

## Outcomes

- Success: `CONTEXT DC3 slot=1 versions=0 empty VM`, then `CONTEXT DC3 consumed
  slot=1`; `DRM probe type=2 job=1 complete=0`; helper `FAULT kind=0 serial=0`,
  `CONTEXT state=2 maps=0 bytes=0 job_error=0 terminal=1`, and
  `PASS attachment timeline point=1`. Runner passes `context-attach park`,
  `context_complete=1`, `parked=1`, `failed=0`, `last=0`, rc0.
  This means DC3 returned; numerical GPU access is still untested.
- Classified kernel timeout: `CONTEXT attach result=-110`, job error -110,
  `context_timed_out=1`, `failed=1`; runner attempts explicit wrapper park,
  logging `PARK failed CONTEXT timeout`. Original -110, failed lock, tables,
  DMA memory and IRQ handling remain. No retry on this boot.
- Firmware fault: `G2 recovery event`, `G2 page-request event`, or
  `G2 channel-error event`, raw 11 words, helper `FAULT kind=1/2/3`
  (unknown type=4), job error -5. Fault blocks ordinary park; firmware's
  reset/page response/channel acknowledgment protocol is not implemented.
  Preserve logs and reboot; memory remains quarantined.
- Host helper/stage deadline: `command-deadline`, rc124, no cleanup behind
  the unfinished worker. Do not retry, wait for a stuck worker, or issue GPU
  commands; reboot. A userspace observer deadline is not a classified kernel
  hardware timeout and cannot authorize park.
- Gate/layout failure: no DC3 kick is claimed; preserve exact errno/logs,
  do not clear the experiment lock or switch frontend on this boot.

The park path is reachable after a **returned, classified** attachment
hardware timeout and validates its exact one published DC slot, other
submission/event rings empty and no event fault. It does not bypass an
unfinished writer, fault, invalid indices or multiple pending submissions.
Park is containment; it never frees DMA or claims recovery/bus quiescence.

Collect the log and strict reconstructed snapshots:

*(Device/host command block omitted; it targets the private workspace.)*

Stages `context-prepared`, `context-kicked`, `context-consumed` or
`context-failed` extend the cmd8 baseline. All sampled RAM remains CPU-visible,
non-atomic observation. No runtime META-local state or heartbeat is inferred.

## Evidence and next compute step

Fresh Ghidra captures in `build/gpu/round12-{slot-host,attach-host,dc3-bytes,events-host}.*`:
`c859a4` publishes a selected slot then conditionally submits DC3 with that
index; `c81794` passes the GART catalogue and packed version getter to
vtable200; raw `c98a60` stores x2 to array[slot*8] and w3 to versions[slot*4].
Firmware handler `1000218c` reads command+4, control1048 indexed by8,
control1044 indexed by4, then calls `10019b84`/`1002700c`. Decoder semantics
are those documented by the firmware-RE agent; no additional MMIO read added.

The userspace agent's in-progress `tools/gpu-userspace/first-dispatch.py`
has a captured constant-store USC, PDS and bounded CDM prefix with relocations.
Its manifest explicitly omits the kernel work object, context helpers and
captured CDM helper tail. Those omissions must be recovered before a
shader launch; a transport fence or DC3 return cannot substitute for stamped
GPU retirement. The dependency-only command never reads channel+8, so its
success supplies no context/work-object ABI evidence.
