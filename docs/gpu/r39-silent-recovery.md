# r39-10 HW Aquarium: silent-loss recovery boundary and punch containment

Generated-by: LLM. Host evidence; new kernel/device qualification pending.
No device command, workspace commit, push or subagent launched by this lane.

## What the device establishes

Orchestrator reports r39-10 numeric 84/84, 20 immediate SW/HW alternating
500-fish Firefox processes, and SW Aquarium 500 with punch enabled all PASS.
Long HW WebRender 500 instead stops at:

```
00:34:37 [6675.385064] RENDER-V3 lost seq=171716 engine=1 slots=12/11 why=3d-silent: context lost, device recovers
```

Source: `build/gpu/r39-10/device/netconsole-churn.log`, 431 lines. Its final
preceding context bind was at 6654.462523. No fault packet, PM OOM record,
failed-job receipt, close/park after loss, or GPU-RECOVER stage survives.
The last wording announces **intent**, not a completed or entered reset.
The exact hardware access that locked the SoC is not observed. Journal/pstore
were not yet available when this packet was prepared.

## Concrete kernel defect: silent loss leaves a window for old-epoch closes

The running source is the VDM warmport topic `fae48f6305477e1a1a9c3c720fcbb40a2133f573`,
source tree `1bc959691db4013f430c164942b2d81bcf46a221`.

1. `g5p_boot_drain()` marks `b->failed=true` on a firmware fault packet.
   A silent stream is instead detected by `g5p_ru_wait_grace()` in the phase
   waiter. It is a host inference, not a firmware fault packet.
2. `g5p_rv3_lose_recover()` previously set only `v->lost` and
   `rd->recovering`, leaving `b->failed/stopped/alive` and the MMIO licence
   unchanged for silent loss.
3. The executor updated `pm_last/pm_prev` even on a failed job.
4. `g5p_rsched_work()` unconditionally called `g5p_render_close_deferred()`
   immediately after the job returned. Its next loop iteration was the
   first check of `rd->recovering`.
5. An old PM owner thereby made eligible for deferred close could pass
   `g5p_ru_close_plan()` (bound, no queued work, no failed/stopped flags),
   issue DC3 close/unbind/park, and call `g5p_rv3_dc_kick()`. That function
   writes R1 wake/readback and, on the old settled-pstate proof, **R0+b00**.
   A firmware fault packet blocked this through `b->failed`; silence did not.

This is a reproducible source-level unsafe recovery path and explains a
specific difference from the earlier ~23 ms firmware-fault recoveries. It
is **not proof that this exact path was reached in the captured lock**:
no following receipt or DC-kick line was retained. Early quarantine and
recovery-stage receipts address both the unsafe path and that attribution gap.

## Kernel fix

Hardware branch `orchard-pr-g5p-20261108/vdm-recover-silent`, commit
`a0e46f30690ca60a3c618ad7c067830b3a23a38f`:

- At loss detection, under the publication event lock, revoke the MMIO
  licence and mark the old boot failed/stopped/not-alive **before logging
  and returning to the scheduler**. Existing ticket users serialize on
  mmio_lock; lock order matches event_lock → mmio_lock in the doorbell path.
- Keep all deferred close references/mappings behind stuck/recovery, both
  at the worker call site and at the deferred-close entry itself.
- Do not advance PM retirement owners on a failed job.
- DC kicks also reject an explicitly gated MMIO epoch before any R1 read.
- Emit recovery begin, IRQ-off, cycle-begin/done and bootstrap stage markers.
  Those are logs, not new GPU-register diagnostics.

The reset sequence remains: software freeze, AIC mask/IRQ synchronization,
verified **PMGR-only** GFX off/on, Fender wake, fresh firmware/shared-state
boot, ALIVE/control proof, new-generation claim, then old-binding release.
No unbind/park of a dead epoch, new raw GPU reset/flush, guessed ISP reset,
new UAPI, DT, power policy or boot-firmware write is introduced. Failed
cycles leave the epoch failed and objects quarantined as before.

Fresh Ghidra evidence is retained in
`build/gpu/r39-recovery/ios-recover.json`: `AGXFirmware_forcePowerCycleAndReboot`
(`fffffff006c9e070`) blocks the scheduler, stops firmware, invokes platform
power off/on, resets context/dependency state, rebuilds shared state and boots.
It does not support an arbitrary host R0 flush after silence. This patch
repairs Linux's admission/publication boundary around its existing reset;
it does not claim to reproduce every iOS hardware reset step.

Only four kernel source files change: `recover.inc`, `drm-render-sched.inc`,
`drm-render-unbind.inc`, `drm-render-v3.inc` (38 insertions, 4 deletions).
The skip-empty-tiles topic changes different files. The packet includes a
both-orders apply check and combined source-tree identity; this kernel
contains recovery only, not skip-empty-tiles.

## 3D silence: what can and cannot be concluded

The r39-10 flight disproves rapid teardown as a sufficient trigger. More
than 400 seconds spread across short contexts passed; the failure was a
long-lived HW context. It does not yet attribute silence to PT2, vk_meta,
parameter memory, or a compiler instruction.

- **Pass mixing:** `pvr_arch_g5p_meta.c` explicitly ends the open subcommand
  and creates separate vk_meta render passes. The blit is not another draw
  inside the seaweed's depth pass. The passes still reuse the context/PM
  machinery and are ordered through transfer-stage sync, unlike SW's CPU
  presentation path. HW adds the RGBA→BGRA GPU blit and WebRender composites.
- **Host TA/3D overlap:** absent. This kernel serializes jobs on one ordered
  worker and waits for TA before publishing 3D; the next job waits for the
  current one. Internal firmware execution/state hazards are not excluded.
- **PT2 vs PT4:** Apple's decoded `getShaderPassInfo` selects PT2 when kill
  mode 1 writes channels that read the destination, PT4 otherwise. Changing
  general blend to PT4 would violate that rule. No encoding change is made.
- **PM pressure / partial render / ZLS:** plausible but unobserved here.
  Existing normal-render ZLS addresses are copied into both upload/runtime
  fields. Apple's alternate tag-2 3D envelope and PM growth/reset work exist,
  but the retained firmware RE explicitly does **not** establish the full
  PM-OOM→partial-render→resume protocol or identify tag 2 as a successful
  captured partial render. No OOM event, PM counters, failed W/SKU or ZLS
  state was captured for seq 171716. A new pressure-handling encoding would
  therefore be a guess, not a fix. See `docs/gpu/firmware-re/README.md`,
  “Round 6”, normal/alternate 3D and fault dump contract.

## Safer Mesa policy

The performance lane already restored shipping default-off in `15ea769ae49`.
Own branch `g5p-r39-recovery-punch-safe`, commit `b89c44046fe`, builds on it:

- General-blend punch remains OFF by default; ordinary GPU blits remain ON.
- Explicit diagnostics require **both** `PVR_G5P_PUNCH_BLEND=1` and
  `PVR_G5P_GPU_BLIT=0`. The failed punch + GPU-meta-blit combination is refused
  non-fatally at pipeline creation, including no-depth base compiler kills.
- `PVR_G5P_PUNCH=0` overrides the diagnostic opt-in in the base compiler too.

This is containment, not a finding that GPU blits caused the hang, and not
qualification of the CPU-blit diagnostic arm. The commit/source patch is
compiled and host-checked; **no new Mesa binary package is shipped here**.
The installed default-off r39-11 package can run the same isolated diagnostic
with both explicit environment variables. Cherry-pick this policy commit
when preparing the next shipping Mesa package.

## Host evidence and limits

- Actual worker body compiled with mocked GPU/reset actions: old silent
  order `J C R J C`, old fault order retained safely; fixed order `J R J C`.
  Both early quarantine and scheduler ordering independently prevent the
  modelled old-epoch doorbell. The real close planner retains failed/stopped
  mappings. Source guards checked against the compiled candidate.
- Private full kernel build, exact VDM config and pristine DT, matching
  modules; stable-serial initrd from the usb-stable-serial topic. Source delta
  and both-order compatibility are verified in the bundle manifest.
- Checkpatch: no code errors/warnings with no-signoff (Orchard forbids invented
  sign-offs) and COMMIT_LOG_LONG_LINE ignored for the description.
- Mesa committed sources streamed and all 13,169 files rehashed; Vulkan driver
  build PASS. 20 policy cases: four real pipeline probes × default, punch-only,
  explicit CPU-blit diagnostic, global-off, explicit mixed combination.
  Refusals are pipeline-time/nonfatal; only the isolated diagnostic admits.
  Fake-node readback failures do not qualify hardware pixels.
- No device access. Hardware recovery after a **real** silent GPU remains
  pending; a clean no-hang flight cannot by itself establish that recovery.

Runbook: `DEVICE-READY-r39-silent-recovery.md` (not published).
