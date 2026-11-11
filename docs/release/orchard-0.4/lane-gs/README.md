# GS2: Apple G5P system sleep — implementation, hardware qualification pending

> **GS4 (2026-11-10):** the pinned never-park envelope refuses sleep after any boot (cold `ready` was the query's unsampled branch); `suspend_ready` now names the reason, and the warm-boot RCU stall was a 330-char emergency printk. See [../lane-gs4/README.md](../lane-gs4/README.md).

## GS3 update (2026-11-10): clients wait instead of failing; readiness query

Not device-proven. Linux `j71t-04/g5p-suspend` (`/src/orchard-linux-gs`) is now `055a9bb12ae8`, three commits
on I2's `6c1b01b2cadc` (backup tag `gs3-backup-gs-6c1b01b2`). Orchard `j71t-04/g5p-suspend` is `e7682d3`, one
commit on `97319a9`, in `build/orchard-0.4/orchard-gs` and fetched into `orchard`.

| Linux | Orchard patch | Change |
|---|---|---|
| `75f12aaec` | `drivers/drm/0026` | drm/apple-g5p: hold clients across the sleep reservation instead of failing |
| `7521b687f` | `core/0003` (byte-identical to suspend's) | PM: sleep: report suspend admission readiness in /sys/power/suspend_ready |
| `055a9bb12` | `drivers/drm/0027` | drm/apple-g5p: answer the suspend readiness query |

**Problem.** GS2/I2 held one host gate from lane S's pre-sync admission until complete. That caused three
failures:

1. Every G5P ioctl, including core syncobj waits, returned -EBUSY at once. Mesa's winsys retries only some
   EBUSY paths; submit and wait errors become `VK_ERROR_DEVICE_LOST` or failed frames.
2. `postclose` spun in a non-freezable `msleep(20)` loop, so a render-node close in the window failed the
   freezer and aborted the sleep.
3. A syncobj wait that started before the window held the host count, and the scheduler worker (gated by
   the same word) could not retire jobs. A busy desktop therefore always failed the 20 ms drain.

Apple's model (iOS trace above): the GPU is gated before system sleep, and the same Metal client continues
after the firmware boots with no error.

**Fix: two-stage admission.**

1. **Client gate.** `prepare` first sets a new client gate (`g5p_drm.client_gate`, closed bit + count). The
   scheduler keeps running, so already-accepted jobs retire. It waits up to `G5P_SLEEP_DRAIN_MS` = 1 s for
   in-flight client ioctls to leave and for `g5p_sleep_idle()`.
2. **Host gate.** Only then does it set the host gate and run GS2's unchanged 20 ms host drain, core lock,
   state checks, boot drain, rings and certificate. Any refusal reopens both gates, wakes waiters and
   returns -EBUSY, as before.

**Client behaviour while the gate is closed.**

- **Gated ioctls** (the default for anything not listed below) wait in `wait_event_freezable()` for
  client + host admission. A frozen waiter never blocks the freezer. If a signal arrives, the ioctl
  returns `-ERESTARTNOINTR`: nothing ran yet, so the call restarts even without `SA_RESTART`. Mesa never
  sees EINTR on SUBMIT, which it refuses to replay.
- **Host-only ioctls** are neither gated nor counted:
  - G5P `GET_INFO`, `GET_EXEC_INFO`, `GET_RENDER_INFO`, `GET_JOB_STATUS`, `GET_CONTEXT_STATUS`,
    `GET_FAULT_INFO`, `CREATE_BO`, `BO_MMAP_OFFSET`, `BO_SYNC`;
  - DRM `VERSION`, `GET_CAP`, `SET_CLIENT_CAP` and the whole syncobj family.

  A syncobj wait may sleep through the transition. GEM close and PRIME stay gated.
- **Closes.** If a file closes while client admission is shut, its `g5p_file` is parked on
  `sleep_closes` (with a `drm_dev_get`) and torn down from `sleep_close_work` once admission reopens.
  Its contexts stay idle survivors, so no close item makes `g5p_sleep_idle()` false. `remove` flushes the
  work after unregistering admission.
- **Reopen.** One helper, `g5p_sleep_reopen()`, serves `complete` and every refusal. It reopens the host
  gate, then the client gate, then wakes waiters, kicks the scheduler and kicks the close work.
  `complete` still reopens after a failed epoch, so clients get the terminal error instead of hanging.

**Unchanged.** Refusal before any destructive step when not quiescent, no MMIO after a sampled power abort,
and freeze + error fences on resume failure. sysfs `command`/`td-kexec` (root debug) still return -EBUSY in
the window.

**Readiness check.** `drivers/drm/0027`, for `/sys/power/suspend_ready`, lane S `core/0003`. It shuts no gate,
drains no events and writes nothing. It returns:

| Result | When |
|---|---|
| -EIO | failed or frozen epoch, sampled power abort (tested before any `readl`), stuck or recovering channel, terminal latch, closed r8 admission |
| -ENODEV | GPU not booted or not powered |
| 0 | in-flight or accepted work (prepare drains it), or the core lock is busy |
| -EBUSY | the GPU is idle but the rings or the certificate fail (e.g. never-park firmware) |

**Validation (host only).**

- Kernel objects are W=1 clean apart from GS2's five inherited `-Wunused-value` warnings.
- `checkpatch --strict --no-signoff`: 0/0/0 on all three commits.
- The export reproduces the branch, and `i2/series-check.py` passes: 7 patches on `bf6ed1829`.
- Integrated build `integration04c`: exit 0, 77 modules, vermagic PASS (see the integration README).
- Orchard suite: see [the Orchard unit suite note](#gs3-orchard-unit-suite).

The live-client device check is `GS3` in `DEVICE-TESTS.md` (not published).

**Remaining risks (device must show).**

- Stage 1's 1 s bound under glmark2: the drain must complete. If it doesn't, the result is a clean
  -EBUSY refusal, not a hang.
- Never-park firmware may still fail the certificate.
- A surviving context's first job after wake reattaches; that path is unproven.
- **A query read can refuse a suspend.** The query holds `system_transition_mutex`, which `enter_state()`
  only trylocks. A `suspend_ready` read that races a suspend request makes that suspend return -EBUSY.
  The file is world-readable, so "no side effects" holds for driver state, not for that race.
- **Prechecks must stay stateless.** The query calls each precheck with the state action but never sends
  `PM_SUSPEND_PRECHECK_COMPLETE`. That is fine for h9p, AOP and dwc2 today; a future precheck that
  reserves in its state action must not be added without a query-aware path.
- **Single-sample certificate.** The G5P check samples the certificate once, while prepare resamples
  for 20 ms. Right after the GPU goes idle, the query may read `not-ready … -16` where a suspend would
  pass. powerd does not retry until wake, so the device check reads the file five times on an idle
  desktop.
- **Mesa contexts are not reported lost.** Mesa `3a00235` never calls `g5p_drm_context_status()` from the
  render path, so `GET_CONTEXT_STATUS` (LOST while `b->stopped`) cannot surface between wake and a
  surviving context's first job. Tasks are frozen across the window anyway.

### GS3 Orchard unit suite

- **First run: invalid.** The `orchard-gs` run imported the venv's editable `build/orchard-0.4/orchard/src`,
  and that shared checkout was mid-merge with conflict markers at the time. That produced 8 extra
  TOML-parse errors.
- **Rerun.** Each checkout used its own `src` (`PYTHONPATH=$PWD/src`, `PYTHONDONTWRITEBYTECODE=1`, macOS
  venv). On `orchard-gs` `e7682d3`: 754 tests, 7 failures, 1 error, 1 skip (`unit-tests-gs3.log` (not published)).
- **Result.** The failure and error names are identical to `unit-tests-gs2.log` (not published): macOS
  root lookup, NFS validation, Wi-Fi random address.

> **Update (lane I2, 2026-11-10).** Linux `j71t-04/g5p-suspend` is now `6c1b01b2cadc` (backup tag
> `i2-backup-gs-e143456`) and Orchard is `97319a9`. The reservation is registered as the suspend topic's
> admission provider (`drivers/drm/0025`), and suspend's `core/0002` and series layer are carried
> byte-identically. See `README.md` (not published).

2026-11-10. Implements bounded sleep reservation, Fender stop/stable-off,
runtime-PM platform off/on and firmware reboot over the retained allocation.
This is source/build delivery, **not demonstrated suspend support**. The
pinned never-park firmware may never meet the quiescent predicate; that stays
an ordinary -EBUSY refusal, without detaching slots or cancelling accepted jobs.

Both owned branches remain `j71t-04/g5p-suspend`. Linux starts at
`6ff1f618428` on pipeline `bf6ed1829b9`; Orchard starts at `d54ce83`.
Final revisions and build receipts are recorded below. Lane G is untouched.

## Implemented contract

- A separate per-device host admission word counts ioctl/VM operations,
  scheduler/close/recovery work and sysfs/autoboot operations. Closing it never
  closes terminal retirement admission or cancels an accepted job. Waits are
  bounded: host users 20 ms, core lock 2 s, certificate 20 ms, DC3 3 s.
- `apple_g5p_system_sleep_ready()` now **reserves** admission when true; it
  checks booted/ALIVE, failures, accepted/queued/ahead/stuck/executing work,
  deferred close/DC, every ring and the latest depth-2 TA/3D stamps, then the
  actual Apple Fender quiescence predicate. Compute epochs conservatively
  refuse because their stamp certificate has not been implemented.
- Lane S must call `apple_g5p_system_sleep_complete()` on every PM_POST_*
  and early abort, including an abort before device PM prepare. The header
  documents this mandatory release. Device prepare is idempotent and complete
  also releases the gate. A true query must never be treated as a snapshot.
- Suspend rechecks the certificate before DC3 detach. After detach, any failure
  is terminal: no blind restoration of bindings. Stop writes Fender mode 3,
  core 0, waits for transition-clear, requests GPC 0, clears ALIVE; IRQ is
  disabled/synchronized before stable-off and runtime-PM put. No raw PMGR poke.
- Wake gets platform power, runs the retained boot/reset FIFO, requests core 0
  then GPC 1 **without a pre-ALIVE active-state poll** (Apple c9f954). IRQ stays
  masked; RAM drain proves fresh ALIVE before the active-state sample, DS108
  claim, IRQ enable or admission release. A witnessed off/on advances DS108
  generation; maps/image validation does not recreate their allocations.
- `g5p_rv3_rebuild_host()` factors recovery bookkeeping under core -> rdev
  order. Clean sleep uses a separate `sleep_rebuilds` epoch, invalidates bindings,
  pm_last/prev, sequence, live maps and submitted/consumed/retired flags, clears
  auxiliary/pool pages and retires host transport one-shots. Both PM1 and PM2
  compare the combined rebuild generation and rebuild on next use. Surviving
  contexts rebind on their next job; BO/VM contents and fence history survive;
  clean sleep never marks ctx->bad or increments recovery/fault streaks.
- Firmware roots and shared ring cursors are retained over wake. No normal-wake
  call to `g5p_recover()`, allocation/map/load stage, context reset or channel/PM
  reset occurs. The first later job rebuilds the detached driver's channel/PM
  state through its existing attach path. That Linux-specific reattachment
  contract needs qualification; it is not claimed as Apple's host reset.
- A resume/partial-transition failure disables IRQ, freezes the boot and MMIO
  licence, closes terminal admission and kicks queued fences to error. Kexec
  refuses MMIO after such failure. Hibernation freeze/poweroff/restore refuse.
  Sleep never consumes the one-shot GPU-KQ latch. No Mesa device-loss guarantee
  is implied by kernel errno; lane M owns its Vulkan mapping.

Source scope adds `drivers/gpu/drm/apple-g5p/system-sleep.inc`, with changes to
core/boot/teardown and DRM ioctl/render/scheduler bookkeeping, and
`include/linux/apple-g5p-pm.h`. No parameters, machine checks, config changes,
new tests, device access, m1n1 tree access, push or GitHub edits.

## Apple evidence

Target confirmed through Ghidra get_program_info: iOS 16.7.10 / 20H350,
`kernelcache.release.iPad6,11_12`, SHA256
`c6b95fcf0efe…`.
Addresses below are unslid, with full `fffffff` prefix. Existing meaningful
function names were retained. Fresh decompilations rechecked these paths;
GS comments were added at `fffffff006c7f434`, `fffffff006c83d28` and
`fffffff006ca0f78`. Save receipt: `ghidra-save.log` (not published).
Earlier detailed vtable analysis is in
recovery108-apple-power-state-re.md.

| Address | Function / observed behavior |
|---|---|
| `fffffff006c7f3e0` | AGXAccelerator_setPowerState: ordinal at acc+d20. With gating enabled, ordinal 0 runs off action; ordinal 1 runs platform-on/firmware boot then enables scheduling. |
| `fffffff006c83d28` | powerOffGateAction calls powerDownIfQuiescent(idle=0), subject to global flags and gating support. |
| `fffffff006c81b18` | powerDownIfQuiescent: requires booted, alive/not boot-waiting firmware, drained event ring, Fender quiescent and all stamps reached. Stops firmware, disables event sources, removes platform power, then acknowledges IOPM. If already idle-gated (d21=2), ordinal 0 just records off and acknowledges. |
| `fffffff006c9fa10` | stopFirmwareForPowerDown: live Fender arm requests core power 0 then GPC state 0; clears fw+cad (ALIVE). Non-Fender arm halts META via slave port. |
| `fffffff006ca0f78` | setPlatformPower: ordinary off asserts stable-off, calls provider clock then power operations, clears Fender accessibility and records d21=0. Recovery's fw+212 exception is a different path. Emits 0x85930c0c/on and 0x85930c10/off. |
| `fffffff006c83b18` | powerUpPlatformAndBootFirmware: platform power on, prepare hardware, enable event sources, boot/wait; panic on failed boot. Final virtual +7b0 is a RET stub. |
| `fffffff006c9fc10` | prepareHardwareForBoot: Fender setup and META slave-port preloads, SLC/BIF idle preparation. Does not reallocate user contexts. |
| `fffffff006c9f954` | bootFirmwareAndWait: Fender core 0, request GPC 1, wait for ALIVE. No pre-ALIVE GPC-on polling in this body. |
| `fffffff006c83630` | resetContextAndDependencyState: recovery resets idle GART slots/generations, dependency records, PM objects and work queues. Separate from ordinary wake. |

Raw vtable check: `fffffff006ff6fd0` (G5P address point +7b0) contains
`fffffff006ca86ac`; bytes there are `c0 03 5f d6` (AArch64 RET). Ghidra has
no defined function at that stub; no invented symbol was assigned.

**Conclusion:** normal Apple sleep stops firmware and removes outer platform
power; wake boots over retained shared memory. There is no context/channel/PM
reset call in that wake path. The separate recovery reset must not be mistaken
for the normal sleep contract. This is static evidence, not a live sleep trace.
Provider internals and firmware retention correctness in our pinned, never-park
Linux epoch remain unqualified. The exact follow-up probe is in DEVICE-TESTS.md.

## Validation

GS2 receipts: `build-gs2.log`, `build-gs2-final.log`, `unit-tests-gs2.log`,
`export-gs2.log`, `artifact-sha256-gs2.txt`. Final results:

| Receipt | Result |
|---|---|
| Linux | `e143456f98f6627b32626c1b40b3d8dd0a1bde0a` |
| Orchard | `780978517eb7aa3c738239f4f40362501945a7b3` |
| Export | DRM 0024; exporter verifies exact reproduction on `6ff1f618428` |
| Kernel | Image.gz + dtbs passed, exit 0; `7.3.0-rc1-orchard04-gs2`; five inherited unused-expression warnings, no new warning |
| Orchard suite | 754 tests / 291.450 s; 7 failures, 1 error, 1 skip; failure names exactly match prior GS and lane-G baseline (macOS root lookup, NFS validation, random Wi-Fi address) |
| Style | checkpatch 0 errors / 0 warnings with FILE_PATH_CHANGES and MISSING_SIGN_OFF ignored under the no-Signed-off-by policy; git diff --check clean |

Artifacts: `build/kernel-orchard04-gs2/{Image.gz,s8003-j71t.dtb,.config,
COMMIT,RELEASE,DIRTY}`, with clean source status and SHA256 receipt. These are
compile artifacts, not a packaged boot entry. No Python implementation or
converter code changed after the unit suite.

Host free space stayed 34–35 GiB, volume free space 9.1–9.9 GiB through builds,
above both stop limits. GS2 scratch copies/formatting tooling and its generated
build objects are cleaned after saving artifacts. The Linux worktree, Orchard
checkout, commits, exported patch, reports and compile artifacts remain.
No other lane's objects/caches/images were removed.
GPU ms/frame, busy % and fps before/after are **unmeasured**. See
`DEVICE-TESTS.md` (not published) for assumption-specific probe evidence,
stop conditions and the ordered Linux qualification. Keep sleep capability
unqualified in device data until that flight succeeds.

## iOS system-sleep trace, 2026-11-10 (kdebug trace)

Raw: `build/gpu/ios-sleep-20261110/run-gs-sleep{,2,3}` (private). The recorder captures classes 0x8593/0x8518/0x8509/0x8590.
- Run 1 (USB connected, 60 fps Metal workload): no system sleep. The trace clock ran continuously and the frames had no gap.
  Screen-off is not system sleep.
- Run 2 (USB unplugged, no workload): trace span 200.7 s over 300 s wall, so ~100 s of real sleep. The sleep moment
  couldn't be placed: no wall-clock marker.
- **Run 3 (USB unplugged, 1 fps Metal heartbeat with wall-clock stamps): sleep = a 62 s wall jump between heartbeat
  frames 92 and 93.**
  - mach 985.642 / 985.645: `platform-on 0x85930c0c` / `boot-received 0x85930c18`; frame 92.
  - mach 985.687: `platform-off 0x85930c10` + idle-gate `0x85930c14`, 40 ms after the frame.
  - (system sleep, 62 s; the GPU is already off).
  - mach 986.050 / 986.054: `platform-on` / `boot-received` (firmware boots); frame 93 at 986.650 from the **same
    Metal process**.
- **Conclusion:** iOS has no distinct GPU system-sleep path on A9. The GPU is idle-gated (firmware stopped, platform
  power off) before the system sleeps. Wake runs the ordinary platform-on + firmware boot, and the client's
  contexts/queues survive the firmware reboot. iOS idle-gates after every ~40–50 ms idle gap: after the workload, about
  140 off/on/boot cycles per 10 s. This matches GS2's design (stop firmware, platform off, boot over retained shared
  memory, no context reset) and makes the stop/boot cycle a routine path, not an exception.
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
