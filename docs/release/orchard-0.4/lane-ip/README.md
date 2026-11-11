# Lane IP: G5P firmware idle park, the Apple way (host only, not device-proven)

2026-11-10, Opus 5.5. No device access, no push, no GitHub edits, m1n1 tree not opened.

| Repo | Branch | Head | On |
|---|---|---|---|
| Linux `/src/orchard-linux-gs` (volume `linux-a9-src`) | `j71t-04/g5p-suspend` | `c5d09f005` | GS4 `8bc223aeb` (backup tag `ip-backup-gs-8bc223aeb`) |
| Orchard `build/orchard-0.4/orchard-gs` | `j71t-04/g5p-suspend` | `b03bbbb` | GS4 `44f1c94` |
| Orchard integration `build/orchard-0.4/orchard` | `j71t-04/integration` | `b7ed084` | `db2da74` (tag `ip-backup-integration-db2da74`) |
| omarchy-a integration | `j71t-04/integration` | `a7d2ddd` (DP3) | |
| Linux HEVC rebase (branch in `build/orchard-pr2/cs/lane-o-linux`; its sparse worktree was removed) | `ip/vxd-hevc-on-suspend` | `7819ec5cc` | `564a3550e` + VXD suspend `df6a11663`, `819cd515e` |

| Linux | Orchard patch | Change |
|---|---|---|
| `a192cb582` | `drivers/drm/0030` | drm/apple-g5p: let the firmware park itself at idle, as iOS does |
| `c5d09f005` | `drivers/drm/0031` | drm/apple-g5p: certify system sleep on the firmware's own park |

## 1. Finding: the veto is `ctrl+0x20`, not the pin or the sampler

The brief assumed the fix was "sampler on, pstate not pinned". It isn't. The firmware ignores both for parking. What
stops it is one host word that Linux never wrote. The pin and sampler matter for the *wake* (§1.3).

Ghidra (20H350 j71t, `c6b95fcf…`) for the kext, plus the META firmware disassembly (regenerated:
`scripts/gpu/extract-agx.sh`, `build-metag-binutils.sh`, `disassemble.py`, `minim.py` → `build/gpu/firmware-re/`).
Labels: [V] verified decode, [I] inferred.

### 1.1 Who decides to park [V]

- The governor `0x1000c0d8` ends every pass in the idle tail `0x10009bd8`. If the deadline hasn't passed it goes there
  directly (`0x1000c838` → `B 0x10009bd8`); otherwise it goes through the state-0 recompute (`0x1000c830`). This holds
  with the sampler off: the deadline is `now + policy+4 · 24000` (`0x1000c708`), so `policy+4 = 0` just recomputes
  every pass.
- The tail's vetoes, in order:
  - **`priv+0x188 ≠ 0` (`0x10009bec`)**;
  - `policy+0x34 ≠ 0`;
  - the engines are idle (`0x100013f4`);
  - every root ring is empty (`0x1000176c`);
  - `0x10001bdc == 0` and `0x1001ee98 == 0`.

  Only then does it call the try-park wrapper `0x1000968c` → `0x1001cec8`, with target `policy+0x28`.
- **`priv+0x188` is `ctrl+0x20`.** The firmware refreshes `ctrl+0/4/0x10/0x14/0x18/0x20` into
  `priv+0x170..0x188` on every tick (`0x1001061c` → `0x10001328`; the copy is at `0x10001388`). A host write therefore
  acts without a reboot.
- **The kext writes `ctrl+0x20 = platform+0x510 & 1`** (`fffffff006c97888..94`, in an undefined code region after
  `AGXMetaFirmware_initializeSharedRootsAndControl`; disassembled from raw bytes). J71t's platform word is `0x00200545`,
  so iOS runs with 1. Linux wrote 0, so the tail returned on every pass: **no Linux epoch has ever been able to park.**
  This is design note U5 (`apple-idle-power-design-20261109.md`) answered.
- The same bit picks the submit branch in `AGXMetaFirmware_submitDeviceControl` (`fffffff006ca05d4`). With it clear, a
  GPC read at 0 with `R1+0 == 0` forces a power cycle and reboot. With it set, the kext only reads back and rings.

### 1.2 What the park leaves, and why Apple's certificate needs it [V]

`0x1001cec8` runs these steps:

1. The full drain `0x1001b638`.
2. `R1+0x1004` = target (`0x1001cce0`).
3. `R1+0 |= bit 29` (`0x10007a44`).
4. An abort if a ring took work (`0x1001cd8c`).
5. Otherwise it **keeps bit 30 only when `priv+0x188 ≠ 0`** (`0x1001cf74`), runs `setter(0, 0, 1000)` (GPC 0), then
   self-branches at `0x1001d074`.

That leaves `R1+0[30:29] = 11`, GPC 0 and `R1+8 = 0`, which is exactly `AGXMetaFender_isQuiescent`
(`fffffff006ca66e4`). Apple's sleep certificate is therefore written for `ctrl+0x20 = 1`.

### 1.3 The wake reboots the firmware, so the policy record must be iOS's [V, one step I]

- A parked firmware never returns from `0x1001d074` [V]. Every firmware boot runs the unpark handshake
  `0x1001cd8c(1)` (`0x10000b88`, reached from `0x10000b0c` when `priv+0x228` = `meta+0x6c0` ≠ 0: `R1+0 = 0x40000000`,
  `R1+0x1004 = 0`, W1C `R1+8`), then the boot sampler `0x1000aa80` (`0x10000b54`), then the scheduler `0x8000a0a0`
  (via `0x100271ac`) [V].
  - The scheduler has no return: every branch in its body goes back to `0x8000a0fc`.
  - The sampler's only caller is `0x10000b54`, and its `+0x918` store (`0x1000ab44`) is the only one.
  - So the sampler runs **once per firmware boot** [V].
  - That the kick or doorbell actually restarts META from its reset vector is [I]: it is the only exit from the
    self-branch, and iOS's capture shows `policy+0x34` 0 → N across each wake. The flight's IP2 tests it.
- The host side is Apple's submit order (Fender vtable `fffffff006ff6290`):
  1. `+0x80`: `R1+0x14 = 7`, then a read-back;
  2. `+0x18`: one GPC nibble read;
  3. at nibble 0, `+0x70`/`+0x78`/`+0x90` reads only;
  4. `R0+0xb00 = 0x10` **at any nibble**.
- The boot sampler stores `policy+0 = 1` in its first-call init (`0x1000aec8`). On every later boot it takes the
  sampling path: elapsed / 24000 / **`policy+4`** (`0x1000ac10`, `0x1000ac28`; libgcc-style `0x10022f88`, divisor 0 →
  `0x10023274` → `0x10000260(1, 0)`).
- With the pinned envelope (`policy+4 = 0`), a pinned firmware that parked would wake into a division by zero. Its
  outcome isn't settled statically. Seed 2's load-governor path at a stale stamp ended with "no ALIVE, Fender 0" on
  hardware (perf-envelope.h). **So "pin + park" isn't safe, and iOS's record is the only configuration Apple runs
  through this path.**

### 1.4 What else `priv+0x188` changes [V, I]

- The three MTS job-start functions `0x80000d50`, `0x80001c68`, `0x80003588` (`0x80000d6c`, `0x80001c80`,
  `0x800035a0`; no static caller, dispatch table [I]) differ by this bit:
  - with `priv+0x188 = 0`, they first run `0x100130a0` on the context and, if it returns nonzero, an activity record
    `0x1000e768`;
  - with it set, they go straight to `0x10012b30`.
- So Linux has been running a job-start path that J71t's iOS never runs.
- [I] It is a candidate for the `policy+4 = 16` "TA consumed, never started" wedge (latency123 boots 2/3, T2/T3). Every
  sampler flight so far ran at `ctrl+0x20 = 0`, so that evidence doesn't transfer to this configuration either way.

### 1.5 Earlier experiments and their DFU records

- **latency123 boots 2/3, T2/T3** (`policy+4 = 16`, `ctl20 = 0`): first TA consumed, never started; 60 s timeout,
  DEVICE_LOST. Warm-recoverable. "Do not use" (`a9-gpu-status-20261102.md` §5.3).
- **nopatch B2** (iOS inputs with **`ctl20 = 1` before release**): first-ALIVE read `state=00000000` (parked),
  `R74E ALIVE submit … ret=-112 … power_abort=1`, and the hops back failed (`nopatch.md` ~403). That is the park
  happening before Linux's bring-up proofs, so this lane arms the bit only after bring-up.
- **Seed 2** (pinned record, `policy+0 = 1`, `+4 = 16`, stale `+0x8f8`): no ALIVE, Fender 0 (perf-envelope.h).
- **rung 5** (park mode with licensed R0 reads): SoC freeze. Hence the R0 refusal in park epochs.
- **`idle_fw_policy` patch 0027**: the same record plus `ctl20 = 1` at map; built but **never flown**. It would have hit
  B2's abort.

Ghidra changes, saved (`ghidra-save.log`):
- disassembly comment at `fffffff006c97894` (the `ctrl+0x20` store);
- decompiler comments on `submitDeviceControl` (Fender vtable decode) and `isQuiescent`;
- renames `AGXMetaFender_isFirmwareParkFlagSet` (`ca6624`) and `AGXMetaFender_kickRegisterBit1` (`ca6664`).

## 2. Design (fixed policy; one debugfs control for qualification)

**`drivers/drm/0030` (Level 1).**

- **Map.** `g5p_perf_install()` keeps the pstate table. `g5p_park_install()` (the self-park block in
  `perf-envelope.h`) then writes iOS's record:
  - the kext's coefficient block and filter init (47 words, identical in six J71t captures, 3851 mW envelope);
  - no override (`ctrl+0x1038/0x1040 = 0`, `policy+0x68c/0x6f4 = 0`), ceiling 400, `meta+0x6c4/0x700 = 1`;
  - a fresh record (`+0 = 0`, `+4 = 16`, state 0, substate 4, target 1, duty 1.0), and `ctrl+0x20 = 0`.

  The release powers the GPC on at 1, as `bootFirmwareAndWait` does. No module parameter and no machine check: G5P is
  J71t-only, so these are its constants, like the pstate table.
- **Arm.** `g5p_park_set()` writes `ctrl+0x20` in the live control object, then a barrier and a Normal-NC read-back.
  - It arms only on a complete epoch: ALIVE, control complete, nothing failed or stopped.
  - It runs at `autoboot complete` and after a successful in-boot recovery.
  - The first arm latches `park_epoch` for that firmware boot.
- **Doorbells.** In a park epoch every doorbell follows Apple's order: the r74f bells, `g5p_rv3_dc_kick`, the wake110
  path (`g5p_wk_io.park`) and the shared `g5p_prepare_kick`.
  - The existing 2 ms settle still runs. If the GPC still reads off or in transition, the bell rings anyway, which
    Apple does at any nibble.
  - The only refusal is `R1+0 == 0` (a dead wrapper, where Apple power-cycles and we don't). That is the fail-closed
    edge.
- **PM record.** In a park epoch every TA carries its PM record (tag6), as before `85670a5c9`'s clean-PM shortcut.
  That shortcut was measured only on never-park epochs, and a parked GPC loses power between two jobs. The cost is
  the per-job record the pipeline had before this morning; IP4 measures it.
- **R0.** `g5p_mmio_r0_regime_ok(gpu_perf, park_epoch, override)` refuses every R0 ticket in a park epoch before any
  bus access. That includes the fault banks, so their diagnostics are lost in park epochs. Apple reads them only with
  the firmware stopped.
- **Observability.**
  - `idle_power_status` adds `self_park armed park_epoch ctl20` (RAM only).
  - debugfs `dri/N/g5p_self_park` (0600) prints the latches and the record's live words (RAM only). It accepts
    `park 0|1` and `pin 0|100..400`.
  - `pin N` writes the kext's own override inputs (`ctrl+0x1038 = 400`, `ctrl+0x1040 = N`). The governor copies them
    into `policy+0x68c/0x6f4` (`0x1000a74c`, `0x1000c568`), so the target is N/100 from the next park → wake.
  - These controls exist for the flight's A/B only. The fixed policy is park on, pin 0.
  - **`park 0` is not integration-e's never-park.** On g it leaves the sampler at 16 ms with `ctrl+0x20 = 0`, which is
    the latency123 T2/T3 configuration that wedged the first TA. The flight never uses it (stop condition S6). An epoch
    whose arm was refused is in the same state, so it fails closed only up to its first job.

**`drivers/drm/0031` (sleep).**

- `never-park/*` now means the park isn't armed (`ctrl+0x20 = 0` in RAM, or the arm was refused).
- prepare's certificate wait is 50 ms (was 20 ms).
- suspend re-samples the certificate for the same 50 ms bound after the DC3 detach. The detach wakes a parked firmware,
  which parks again once its rings drain.
- resume disarms `ctrl+0x20` and clears `park_epoch` before the retained boot, so its ALIVE/GPC proofs run on a
  firmware that can't park. It re-arms after the DS108 claim.

**Paths checked against a parked firmware (static).**

- **The first job's DC3 attach.** `g5p_rv3_attach` → `g5p_r74f_bell` rings at once. In a park epoch a GPC that reads
  off no longer returns `-EHOSTDOWN`, so the bell never takes the ALIVE-deferred path (`g5p_r74f_alive`) or the r74e
  GPC 0/1 reactivation.
  - Mid-epoch ALIVE events from a woken firmware only set `alive` again. A healthy R74 epoch already posts about
    290 per second (heartbeat116.h).
- **Kexec quiesce.** It detaches through `g5p_rv3_unbind_slots` → `g5p_rv3_dc_kick`, which rings a parked firmware.
  Its Fender stop is Apple's stop of a parked firmware.
- **Recovery.** The freeze and PMGR cycle run on a parked firmware too. The new epoch maps a fresh record
  (`ctrl+0x20 = 0`) and re-arms after its claim.

**Unchanged:** every GS2/GS3 gate, the stop sequence, platform-off, freeze + error on failure, no MMIO after a sampled
power abort, and all bounded waits.

**Depth-2 pipelining and GS3's client hold.**

- The firmware parks only when every root ring is empty and the engines are idle. While a depth-2 "ahead" job is
  published it can't park, and a park that races a publish aborts (`0x1001cd8c`).
- Every publish rings, and the bell wakes a parked firmware.
- While GS3's client gate is closed nothing publishes, so a parked firmware stays parked: that is the state the
  certificate wants.

**Topic placement.** Both commits sit on `j71t-04/g5p-suspend`, not a new `g5p-idle` topic between pipeline and suspend.

- 0030 doesn't need the suspend code, but it edits the same hunks GS2/GS3 changed (`struct g5p_boot`, `a9-gpu-drm.c`
  probe/autoboot, the bells). Moving it before them would mean rebasing and re-exporting GS's nine reviewed patches
  (0023–0029, core 0002–0004) and invalidating their receipts.
- 0031 depends on GS2–GS4.
- If the maintainer wants the split at publish time, 0030 rebases onto pipeline with context-only conflicts.

**Not done: Level 2 (host platform-off ~40 ms after idle).**

- iOS powers the platform off after ~40 ms of quiet (`powerDownIfQuiescent` `c81b18` via the idle timer `c83d88`).
- Linux's equivalent is GS2's suspend/resume pair (stop, platform off; boot over retained RAM). That pair detaches every
  slot and rebuilds host state each time, and it has never been flown.
- Level 1 already gates the GPC and makes the sleep certificate reachable. Level 2 should follow once IP6/IP7 prove
  GS2's stop/boot, as a delayed work that calls the same stop/boot primitives.
- Exact shape for that follow-up:
  - drain the client gate the way prepare does;
  - wait 40 ms after the last retire, re-arming every 5 ms if the certificate fails;
  - the first gated ioctl queues the resume and waits on `sleep_wq`.

## 3. Build and validation (host only; host tests are not hardware results)

- **Kernel objects.** `a9-gpu-drm.o` was built at each commit, plus `kernel/power/suspend.o`: W=1, Debian clang 19
  (`localhost/orchard-hardware-kernel-toolchain:bookworm`), in-tree. Only GS2's five inherited `-Wunused-value`
  warnings.
- **checkpatch.** `--strict --no-signoff`: 0/0/0 on both commits.
- **Export.** "applied to 8bc223aeb they reproduce j71t-04/g5p-suspend exactly".
- **Series check.** `i2/series-check.py`: PASS, 12 patches on `bf6ed1829b9` (`ip-series-check.log`).
- **Catalog.** `tools/catalog/generate matrix`: no change on `orchard-gs`.
- **Orchard suites.** macOS venv, `PYTHONPATH=<checkout>/src`, failure names identical to GS4's:
  - `orchard-gs` `b03bbbb`: 754 tests, 7 failures, 1 error, 1 skip (`ip-orchard-gs-tests.log`);
  - integration `b7ed084`: 773 tests, 7 failures, 1 error, 3 skips (`ip-orchard-integration-tests.log`).
- **Integration-g.**
  - Orchard `b7ed084`: build exit 0, 559 patches, 77 modules, vermagic PASS, the inherited warnings only.
  - Bundle `orchard-04-integration-g.tar.gz`, SHA256 `7408a869884b…`.
  - The HEVC topic was carried, renumbered to `drivers/media` 0008–0011, and the DP3 overlay is included. See
    the integration README.
- **GPU numbers.** GPU ms/frame, busy % and fps are **unmeasured** (no device access). IP4 measures them before and
  after on one boot.

## 4. Device flight

The flight is `DEVICE-COMMANDS-ip.txt` (not published), prepended to `integration/DEVICE-COMMANDS.txt`. It is a
day flight and DFU-class. Steps, ordered by risk:

| Step | What |
|---|---|
| IP0 | cold bring-up with iOS's record; the arm line |
| IP1 | park observed: `pstate=0` in RAM samples, `suspend_ready` = `ready` when idle |
| IP2 | unpark on new work: glmark2, desktop + Firefox scroll, Aquarium 500 |
| IP3 | 50 park/unpark cycles |
| IP4 | ms/frame and fps: selfpark vs `pin 400` on one boot; never-park baseline = integration-e itself (its GS4 numbers or its kept entry) |
| IP5 | warm boot |
| IP6 | rtcwake from warm |
| IP7 | rtcwake from cold |
| IP8 | idle power: g (park) vs integration-e (never-park), one boot each |

Stop conditions S1–S5 are listed first in the file.

**Predictions and their meaning.**

- **IP1.**
  - Expect `pstate=0` most of the time at idle and at least one `ready`.
  - No park at all would mean another veto holds: `0x10001bdc`, `0x1001ee98`, or engine busy words left set.
  - A certificate that disagrees with RAM would mean R1 isn't what `0x1001cec8` writes on this firmware build.
- **IP2.**
  - A TA that never starts would be the latency123 wedge recurring at `ctl20 = 1`. Check
    `G5P self-park armed why=autoboot` preceded the first client job; arming is asynchronous to the firmware tick.
  - Seed 2's signature ("no ALIVE, Fender 0") on the first job after an idle gap longer than 16 ms would mean the
    woken boot sampler's load path fails on this record. GS2's resume boot (IP6) presents the same stale-stamp record.
  - A hang before any job completes means the kick + any-nibble ring doesn't restart the firmware on Linux. Then this
    lane's Apple-order evidence is incomplete, and the next ask is the iOS probe (`apple-idle-power-probe.sh` U1/U4:
    a park/wake timeline on iOS).
- **IP4.** The iOS governor applies a new target only across park → wake, so gapless load can stay at P1.
  - If `selfpark` is slower than `pin 400`, the fixed policy should become "park on, pin 400". That is the kext's own
    override input, and it changes no code path.
  - Report the numbers; the owner decides.

**Proposed CHANGELOG.** "J71t: the GPU firmware parks itself when idle, as on iOS, so the GPU can certify system sleep
and powers its cores down between frames."
