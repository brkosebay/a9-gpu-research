# Experiment 03 — staged Apple META boot and type-0 alive event

**Round 6 retry:** integrate **`aa8df8a460e92bfc34c3497f8f278a46e851392c`**
(patch 0013) after the already tested `a070663751`. No device retry has
run with this fix. **G2 remains open.** Only the orchestrator operates the
hardware. [Readback evidence](../round6-readback.md) explains the change.

**Verified latest device result:** on Omarchy kernel `a9/integ 1140f36b46`,
runtime activation, firmware validation, wake/ID/META baseline and map all
passed. The revised Fender transition executed at least its reset effects:
R0+100=0, +104=1. The following R0+a18 read never returned and the SoC
hard-locked. This is Run 2 below. The old slave-port load would have repeated
that read even if the snapshot had been removed.

**Implemented fix, device untested:** after arm starts, slave-port access
and later ID/META sampling are rejected before MMIO. Arm snapshots read
only the two reset halves, already observed returning in that state.
Catalogue/scratch/SLC remain programmed through the FIFO but **are not read
back**. Load verifies mapped coherent RAM; release executes Apple's full
FIFO ending reset=0, then uses RAM events. Post-release/failed-transition
snapshots collect wrapper words only. `result`, `registers` and `queues`
are cached/CPU-only sysfs reads with no GPU transaction.

**Verified Apple host sequence:** loader `...6c9f1bc` copies firmware and
writes the segment/LDR configuration to mapped RAM; `...6ca43b0` builds the
13 segment pairs. `...6c9feb4` builds the complete reset/MMU/SLC FIFO with
final reset=0; `...6c9f954` starts Fender and waits for the firmware event.
**Inferred Linux composition:** retaining a reset-held arm checkpoint and
minimal zero policy fields, then replaying the complete FIFO, still requires
device validation. A matching reset read proves that gate only; firmware
alive is the validation of the remaining path.

## Exact next run under Omarchy

The orchestrator should integrate patch 0013, build the integration tree,
and fresh-boot with **no GPU bootargs**. Keep the DRM frontend and optional
work probe disabled. Firmware is already installed by the orchestrator at
`/usr/lib/firmware/apple/agx-g5p-c0.ldr`, 119112 bytes, SHA256
`33ae20cbbe24…`.
Retain the existing netconsole receiver throughout the test.

Upload run-experiment.sh to
`/tmp/run-experiment.sh` using the existing SSH transfer path. In a **root
SSH shell** on the device:

*(Device/host command block omitted; it targets the private workspace.)*

From an unprivileged shell, use `sudo sh -c` for the parameter writes and
`sudo sh /tmp/run-experiment.sh` for the runner; `sudo echo` alone does not
privilege a shell redirection. Runtime activation on this kernel was verified
by Run 2. No HoolockRD-specific tool is used inside the runner. Its plain
sh/sysfs/proc/dmesg path works under Omarchy. Keep the full output and
netconsole log; paste the complete `G5P SUMMARY BEGIN` through `END` block.

**Fallback HoolockRD transport, orchestrator only:** same fixed integration
kernel, bootargs `a9_gpu_diag.enable=1 a9_gpu_diag.boot_experiment=1`, then:

*(Device/host command block omitted; it targets the private workspace.)*

Do not change boot environment solely to hide this register bug; the fix
removes its access in either environment. Start from a fresh boot and do
not run experiment 01, devmem scans or unrelated debugfs tests first.

## Stages and expected gates

The single upload performs all prerequisites, then stops at its first
nonzero sysfs return, `last`, `failed` latch or missing success flag.

| Stage | Expected result / evidence |
|---|---|
| validate | Exact firmware hash and all 94 LDR records accepted; no GPU access. |
| prepare | `loaded=1`, 0x30000 CPU bytes, T1 PC=20000000/SP=8000b3c8. |
| wake | PMGR active, Fender status 00000001; known prerequisite sequence. |
| id | Revision 00090f00 / ID 011b0602, legacy BVNC 9.15.6.2. |
| sample | Pre-reset META baseline only; same successful state as experiment 02/Run 2. |
| map | 45 independent 16 KiB coherent allocations, 42 PTEs, four leaves; run-specific catalogue PA. No GPU MMIO. |
| arm | GPC 0 → core request 20 → verified 41-word FIFO → core 0/GPC 1. Raw R0+100 and +104 only; expected 0/1. `G2 reset-held gate verified`, `armed=1`. No a18/ac8/BIF/SLC read. |
| load | CPU comparison of all 12 mapped image pages including boot config; DMA barrier; `G2 RAM load verified bytes=30000 segment_pairs=13 LDR_pairs=27; no slave-port MMIO`, `copied=1`. No readiness polls/probes or slave writes. |
| release | Replays complete original 45-word stream including final reset=0, same bounded Fender transition; `released=1`. Wrapper-only snapshot. |
| events | Within three seconds, firmware producer advances; raw 44-byte event type 0; `G2 ALIVE`, `alive=1`. IRQ174 count is independent routing evidence. |

**Acceptance:** a firmware-owned type-0 event. A reset word, enabled thread,
CPU image comparison or successful FIFO write alone does not establish G2.
`alive=1 irqs=0` proves polling progress but leaves IRQ routing open. Repeat
from a fresh boot before treating firmware boot as stable. The optional
[CL dependency probe](04-cl-queue.md) is a separate later decision.

**Readback policy:** baseline automatic snapshot uses twelve returning
clock/ID/reset words (no slave/MMU aperture). After arm, only 100/104 are
cached. Off/busy/unknown transition or after release: no R0 snapshot. Later
`meta`/sample and ID requests return EPERM without R0 access. The summary
never initiates a fresh GPU read. It may show only wrapper words after
release; the logged `G2 verify reset actual/expected` preserves the arm gate.

## Bounds and failure handling

Kernel Fender polls are 100 ms for completed reads; event wait is three
seconds, drains at most 16 entries each time, logs at most 256 events and
caps IRQ storms at 256. Per-stage shell deadlines remain
15/15/5/5/5/15/10/20/10/8 seconds. A writer timeout sends TERM and returns
without waiting for its PID, retains the runner lock and skips register/
queue reads. **An uninterruptible bus transaction can still lock the SoC**;
software deadlines cannot recover that failure. No automatic retry/reset.

- **Validate/prepare failure:** collect firmware path/hash and result. No
  GPU access has occurred; the runner still retains its lock for inspection.
- **Wake/ID/baseline failure:** stop; preserve netconsole's last operation.
  Do not try extra probes or assume PMGR active implies register safety.
- **Map/DMA rejection:** collect rejected address/alignment and DMA/CMA
  boot lines. Requirement is 720 KiB in separate 16 KiB allocations, not a
  large contiguous/CMA block. GPU PA/bus translation must be identity.
- **Park/core-ack/FIFO/start timeout:** preserve raw wrapper and stored FIFO
  comparison logs. Failure collection is cached-only by default. Do not
  force clock controls or retry arm on the same boot.
- **Reset readback 0/0 or mismatch:** stop before load. This is a useful
  returning failure; do not bypass it or restore the removed MMU snapshot.
- **RAM load mismatch:** stop before release; preserve the comparison and
  result. Investigate CPU packing/config/copy, with no slave-port fallback.
- **No alive:** preserve result, raw events, queue indices and IRQ count.
  No events vs nonzero event types vs malformed indices are distinct
  failure shapes, not a proven diagnosis. Do not run a post-release META
  sample or MMIO dump.
- **Type 4/7/8, corrupt indices or IRQ storm:** failure latches, backing and
  fault entry are preserved. Reboot before another attempt.
- **Global lock:** retain the last netconsole line and use the owner's DFU
  procedure. There will be no summary if the scheduler/network stops.

Cached collection on a responsive root shell needs no helper upload:

*(Device/host command block omitted; it targets the private workspace.)*

Do not remove a stale runner lock and rerun on attempted maps. No live-DMA
teardown or safe recovery has been implemented. The driver refuses runtime
disable after registration; turning gates off does not cancel active work.

## Offline build

*(Device/host command block omitted; it targets the private workspace.)*

Outputs are `build/kernel-gpu/Image.gz`, `dtbs/s8003-j71t.dtb` and
`build/gpu/initramfs-gpu.gz`; the new manifest records current bytes. Apple
firmware stays under build. Host page size is 16 KiB, largest required
contiguous allocation 16 KiB. The integration tree needs only the targeted
fix for this next diagnostic run; default-disabled DRM can be integrated
separately.

## Results — preserve historical runs

### Run 1 (2026-10-22 ~15:00, orchestrator): preflight→map PASS, arm FAILED at readback (-5)

Integration kernel `7.3.0-rc1-g90aa435537bb` = periph c7c3eb2d34 + pcie
320a9f634d + gpu 56bce69bdb, patched m1n1 (build/m1n1-pcie), bootargs
`panic=0 nvme_core.admin_timeout=15 a9_gpu_diag.enable=1 a9_gpu_diag.boot_experiment=1`,
initramfs `build/gpu/initramfs-gpu.gz`. Logs: `docs/test-logs/exp03-*.log`.

- preflight: SHA256 + 94 records OK; `LDR packed into 30000 CPU bytes; T1 PC=20000000 SP=8000b3c8`.
- wake / id / meta: identical to experiment 02 (Fender status 1; `R0+20=00090f00`,
  `R0+18=011b0602`; `CTRL1=07000040 IRQSTATUS=0`; T0 `0201c032/00020000`, T1 `0201c132/00000000`).
- map: `G2 maps: 45 x 16KiB allocations; 42 PTEs, 4 leaves, PC=0x000000080cf30000`, `maps=1`.
- arm: the Fender wake again, then `G2 init stream: master boot, release=0; FIFO reset`,
  FIFO writes incl. `R0+0e200=3`, `R0+0e20c/208/214/210` (b42dd24b/4bd22db4 pairs),
  `W R1+2010=bf; R1+2014=233`, `R0+0e164=8`, `R0+0e160=0cb04000`, `R0+0bbc=0`, `R0+0bb8=0`,
  `W R1+20000=0; W R1+1000=11`, `G2 FIFO complete status=00000001 ret=0`, then
  `G2 R R0+100/e148 (reset-held/catalogue readback)` → **command arm result -5**
  (`last=-5 ... maps=1 armed=0 failed=1`). **The read values are not logged**
  (neither by arm nor by the status phase). The system stayed alive; stopped
  here per the failure rules (load/release/events not run).

### Run 2 (2026-10-22 ~16:41, orchestrator): runtime Omarchy activation PASS, arm snapshot hard-lock

**Verified from supplied logs/report:** integration `1140f36b46`, GPU
`a070663751`, Omarchy NBD root, Hyprland llvmpipe, no GPU bootargs. Root
runtime enable/boot_experiment succeeded. Firmware in /usr/lib/firmware had
the pinned hash/size. Runner used `timeout 170 sh run-experiment.sh`.
Logs: netconsole and
runner.

Preflight/wake/ID/META/map passed. Map logged 45 x 16 KiB, 42 PTEs, four
leaves, catalogue PA `0x000000081c0f4000`. The revised Fender 0/core20/1
sequence completed, FIFO stored 41 words. After-arm snapshot returned
R0+100=0 and +104=1. It printed `G2 R R0+00a18` with no raw value; 0.54 s
later another CPU logged an I2C timeout, then silence. Ping died; owner
DFU was required. No summary or load/release/events result exists.

**Verified conclusion:** the META port is unsafe in this observed held-reset
state; active Fender did not make it safe. **Inferred internal cause:**
GARTEN/CPU-domain reset blocks the port. The log does not establish complete
MMU/SLC FIFO effects. Fix `aa8df8a460` addresses both the snapshot and the
next load/sample access paths. No retry with that fix is claimed here.
