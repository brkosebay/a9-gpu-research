# GS4: the warm-boot RCU stall and the warm-boot sleep refusal (host only, not device-proven)

> **Lane IP (2026-11-10):** the never-park veto is `ctrl+0x20` (`priv+0x188`, idle tail `0x10009bec`), not the pin. `drivers/drm/0030–0031` arm the firmware's own park with iOS's policy record; `never-park/*` now means "park not armed". See [../lane-ip/README.md](../lane-ip/README.md).

2026-11-10, Opus 5.5. Host work only: no device access, no push, no GitHub edits, m1n1 tree not opened.

| Repo | Branch | Head | On |
|---|---|---|---|
| Linux `/src/orchard-linux-gs` (volume `linux-a9-src`) | `j71t-04/g5p-suspend` | `8bc223aeb` | GS3 `055a9bb12` (backup tag `gs4-backup-gs-055a9bb12`) |
| Orchard `build/orchard-0.4/orchard-gs` | `j71t-04/g5p-suspend` | `44f1c94` | GS3 `e7682d3` |
| Orchard integration `build/orchard-0.4/orchard` | `j71t-04/integration` | `db2da74` | `ed1a0d7` (merge 22) |
| omarchy-a integration | `j71t-04/integration` | `6df5b40` (D3, unchanged) | |

| Linux | Orchard patch | Change |
|---|---|---|
| `2ce21eae7` | `drivers/drm/0028` | drm/apple-g5p: keep the boot perf readback off the synchronous console |
| `597b590d7` | `core/0004` | PM: sleep: let an admission provider name its refusal in suspend_ready |
| `8bc223aeb` | `drivers/drm/0029` | drm/apple-g5p: name the sleep readiness refusal, and refuse never-park |

## 1. The warm-boot RCU stall

**Corrections to the report.**

- It lasted 21 ms, not 85 ms. The 16K config runs `HZ=1000` with `RCU_EXP_CPU_STALL_TIMEOUT=20`, so 21 jiffies is 21 ms;
  `s: 85` is the expedited sequence number.
- The two `G2 Fender park: core=0, GPC=0` lines are normal on every boot. `g5p_boot_program_stream()` runs twice,
  once for arm and once for release. Each run parks first (Apple `c9fa10`: core request 0, then GPC 0), before
  prepare (`c9fc10`) and execute (`c9f954`). Of the first 30 archived G5P logs in `docs/gpu/experiments/logs`, 28
  cold boots show the line twice; one log (a netconsole excerpt) shows it once, and one is a kexec boot.

**Code path.** The stall is not a GPU wait. Every Fender wait sleeps (`readl_poll_timeout()`: `usleep_range` between
reads, 100 ms bound). The R74E/R74F/r1-settle `udelay(10)` polls are bounded at 1.0–2 ms. The `event_lock` sections
hold no wait. The non-preemptible window is inside **printk**:

```
NMI backtrace for cpu 0   Comm: kworker/u8:1   Workqueue: events_unbound g5p_autoboot_work
 console_flush_all <- console_unlock <- vprintk_emit <- _dev_emerg
 <- g5p_perf_readback <- g5p_r73c_fast_control <- g5p_boot_release <- g5p_boot_command <- g5p_run_phase
```

The backtrace is from `build/gpu/r39-8/device-stacks/stacks-sw100/dmesg-before.txt`, an earlier warm boot of the same
driver lineage with the identical `{ 0-.... }` report.

- `g5p_perf_readback()` printed one 320-character `KERN_EMERG` record.
- Emergency records go to every console at any loglevel. `vprintk_emit()` flushes legacy consoles with preemption
  disabled. The compiled J71t DT has `stdout-path = "serial0"`, so `ttySAC0` at 115200 baud is a legacy console.
- That log's timestamps give 87 µs per character: a 53-character line costs 6.1 ms, and the readback line costs
  **29.0 ms**. This is the only boot-path record over the 20 ms threshold.
- The timing matches integration-c. From the second park to the stall report is 113 ms on integration-c
  (6.8487 → 6.9621) and 113 ms in r39-8 (7.4308 → 7.5437).

Because the window is inside printk, sleepable waits, `cond_resched()` and moving work out of atomic context do not
apply.

**Fix (`drivers/drm/0028`).** The same fields are printed at `KERN_INFO` as three records of about 110 characters each.
The RAM reads and the R1-only licence ticket are unchanged. The readback runs after the control submit, so the
hardware sequence and its timing are unchanged.

**Why only the warm boot showed it: not established.**

- Both boots run the readback and have the serial console.
- A report also needs an expedited grace period to start inside the 29 ms window, so a cold boot can hold the same
  window without a report.
- The warm path adds console load. omarchy-a's `orchard-kexec` `warm_options()` strips `quiet` and forces
  `loglevel=7`. In the r39-8 warm log, every G5P `dev_info` line of the arm stream was written synchronously at about
  6 ms per line (a non-preemptible window each) until userspace lowered the console level near 7.4 s. That raises the
  odds and adds boot time.
- Lane D3 owns that choice. GS4 does not change it; it is noted as a follow-up.

**Remaining windows (not changed here, on purpose).** Six more emergency records run on the release path at 10–15 ms
each on the serial console: `DS108 … ev=release/alive`, `R74E power`, `R74E ALIVE submit`, `R73E doorbell begin/end`,
`R74 milestone`, `R74B`. Each is below the threshold. Some sit between the GPC1 request and the first-ALIVE doorbell:
the `R73E` pair brackets the `R0+0xb00` write. Demoting them would take about 50 ms out of bring-up timing. That is a
separate change, to be flown in the day.

## 2. Why the certificate refuses after the warm boot, and why that is correct

**Decision: the state must refuse, after any boot. It cannot be made sleep-safe by a GS-lane change.**

Evidence:

1. **The pin, in this tree.** `g5p_perf_install()` runs on every boot with `gpu_perf = 400` (boot.inc:429/582). It
   sets `ctrl+0x102c` (floor) = `ctrl+0x1040` = `policy+0x6f4` = pin and leaves the sampler off (`policy+4 = 0`).
   perf-envelope.h: "so there is no idle parking at pstate 0". Cold and warm boots use identical values. Kexec mode 3
   changes only the DS108 origin checks and the one PMGR cycle, not the envelope.
2. **Apple's certificate needs the park.** `isQuiescent` (`6ca66e4`) requires `R1+0[30:29] = 11`, GPC nibble 0 and
   `R1+8 = 0`. That is exactly the state the firmware's own idle park leaves (`0x1001cec8`: full drain, GPC 0, bit 29).
   Our pinned firmware never runs that park.
3. **iOS waits for the park and never forces one.** Ghidra (20H350 j71t):
   - `AGXAccelerator_powerOffGateAction` `c83d28` (IOPM ordinal 0) calls `powerDownIfQuiescent(idle=0)` `c81b18`.
   - When the stamps or Fender quiescence fail, that function neither acknowledges nor touches hardware. It re-arms
     through `vt+0x888(1)` and retries per interrupt (`6c80c88`).
   - iOS's system-sleep trace shows why that works there: the GPU is already idle-gated, firmware stopped and platform
     off, about 40 ms after the last frame, so there is no forced path.
4. **Device samples (corroboration only).** On the 1,496 archived pin-400 boot logs (`GPUPERF poweron q=4`), every
   sample reads state 4: about 9.7M `gpc=` (at every bell), 4,312 `r1_1000`, 2,156 `pol34`. None reads 0.
   - These samples are taken at kicks and at boot, not after long idle, so they do not prove anything about idle.
   - The 8,501 `pol34=00000000` samples elsewhere all come from pre-perf60 kernels (no pin, no `GPUPERF` lines).
   - The decision rests on items 1–3.

**Readings that follow.**

- Warm `not-ready 201000000.gpu -16` was the certificate, or the rings, refusing an idle GPU. That is the expected
  answer.
- Cold `ready` was the query's unsampled branch: work in flight, or the core lock busy. GS3's check returned 0 there,
  because "prepare drains it". Under the pin, prepare drains, then fails the same certificate. The cold boot was never
  suspend-ready.
- The difference between the two readings was sampling luck, not firmware state.

**What would make sleep possible** is the iOS Level-1 park: unpin and arm the sampler. That is the idle-power design's
item B/C (`docs/gpu/apple-idle-power-design-20261109.md`, patch 0027 `idle_fw_policy`, never flown). Its known hazards
are:

- an R0 read toward GPC 0 hangs the bus;
- a parked firmware ignored an unrung DC3;
- pins of 200 and above need park → reboot → sampler;
- close/PM faults appeared under park.

It is a GPU-lane day-flight project. A host-forced park has no Apple path; inventing one would be a guessed hardware
sequence, which AGENTS.md forbids. GS4 changes neither the certificate nor prepare.

**Precise reason (`core/0004` + `drivers/drm/0029`).**

- The core gains an optional `reason` callback, called only right after `check` refused, under
  `system_transition_mutex`.
- The token is joined to the device name, so the line keeps three fields: `not-ready <device>:<reason> <errno>`.
- D2's `ipadlinux-suspend-ready` (it requires exactly three words) then prints, for example, "kernel admission refused
  by 201000000.gpu:never-park/gpc=04 (-16)". Its tests are unaffected.
- A token with a space or colon is dropped and the old line is printed.

| Token | errno | When |
|---|---|---|
| `never-park/gpc=NN` | -16 | pinned envelope, GPU idle, sampled GPC state NN (expected `04`) |
| `never-park/busy` | -16 | pinned envelope, `g5p_sleep_idle()` false: work in flight (was `ready`) |
| `never-park/locked` | -16 | pinned envelope, core lock held (was `ready`) |
| `not-quiescent/gpc=NN`, `not-quiescent/r1_0=X/r1_8=Y` | -16 | unpinned envelope, the certificate's own reads failed |
| `ringN=C/P`, `ringN-unreadable` | -16 | a firmware ring has not drained (distinguished from the certificate) |
| `sleep-failed`, `no-boot`, `firmware-failed`, `power-abort`, `terminal`, `recovering` | -5 | as GS3's -EIO list, split |
| `not-booted`, `not-powered` | -19 | as GS3's -ENODEV list, split |

- The sampled reads are the certificate's own reads, in its order, under its conditions: idle, core lock held,
  powered, MMIO licensed.
- A sampled GPC 0 falls through to the full certificate, so a firmware that does park is judged as before.
- The never-park test is RAM-only (`policy+4`, `gpu_perf`).
- prepare, suspend, resume and the certificate are byte-identical.
- One cost remains: a direct `echo freeze > /sys/power/state` still runs prepare's 1 s client drain before refusing.
  powerd reads `suspend_ready` first, so idle attempts do not reach it.
- **PLAN's "s2idle already works" is consistent with this.** Those suspends ran without the G5P driver active.
  `docs/power/suspend-release-readiness.md` item 6 vetoes GPU experiment drivers, and lane D's G5P session postdates
  them. With G5P bound, no boot can sleep until the firmware park lands.

## 3. Validation (host only; host tests are not hardware results)

- Kernel objects `a9-gpu-drm.o` and `suspend.o` are W=1 clean (Debian clang 19, in-tree) apart from GS2's five
  inherited `-Wunused-value` warnings.
- `checkpatch --strict --no-signoff`: 0/0/0 on all three commits.
- The export reproduces the branch (`build/orchard-0.4/gs4-export.log`). `i2/series-check.py` passes: 10 patches on
  `bf6ed1829b9` (`gs4-series-check.log`).
- `tools/catalog/generate matrix`: no content change.
- <a id="receipts"></a>Orchard suites (macOS venv, `PYTHONPATH=<checkout>/src`):
  - topic `orchard-gs` `44f1c94`: 754 tests, 7 failures, 1 error, 1 skip, names identical to GS3's baseline (macOS root
    lookup, NFS validation, Wi-Fi random address), `gs4-orchard-gs-tests.log`;
  - integration `db2da74`: 773 tests, 7 failures, 1 error, 3 skips, names identical to GS3's integration run,
    `gs4-orchard-tests.log`.
- Integrated build `integration04e` (Orchard integration `db2da74`):
  - exit 0, 553 applied patches (550 + 3), 77 modules, vermagic PASS;
  - warnings are GS2's five inherited ones only;
  - the Image contains the new strings (`never-park/busy`, `never-park/locked`, `not-ready %s:%s %d`, the split
    readback);
  - receipt `build/orchard-0.4/integration/build-receipt-e.json` (c's `build-receipt.json` and `dt-check.txt` are
    historical); `j71t.dtb` is byte-identical to c/d's, so the hop into e uses the `file` loader.
  - Log: `build/orchard-0.4/integration/kernel-build-gs4.log`.
- Bundle `orchard-04-integration-e.tar.gz`, SHA256 `a592a804473b…`:
  - integration-d's userspace, asserted byte-identical;
  - a fresh initrd with the stable USB identity and the compiled J71t DT asserted.
- `build/orchard-0.4/integration/DEVICE-COMMANDS.txt` is refreshed. d's packet, manifest and commands are kept in
  `integration/prev-integration-d/`.
- GPU ms/frame, busy % and fps: **unmeasured** (no device access). The device test records them before and after.
- Disk stayed at 29 GiB free on the host and 6.3 GiB on the volume.
- Two objects plus `prepare` were compiled in-tree in `/src/orchard-linux-gs`; their outputs are git-ignored. No other
  lane's caches, images or trees were touched.

## 4. Device test

`DEVICE-COMMANDS-gs4.txt` is prepended to `build/orchard-0.4/integration/DEVICE-COMMANDS.txt`. It covers:

1. cold boot, facts (cmdline, consoles, printk, `idle_power_status`, key dmesg lines), glmark2 build with GPU
   ms/frame, and five `suspend_ready` reads;
2. warm restart, the same facts, the RCU-stall check and the same reads;
3. one `rtcwake -m freeze -s 20` from the warm boot, with glmark2 before and after.

GS4 predicts:

- no RCU report;
- both boots read `never-park/…`;
- a clean, fast rtcwake refusal with the desktop unaffected.

Any plain `ready`, or a real `GPU-PM off`/`on` pair, overturns §2 and is the stop-and-capture case.

## 5. Draft PR text (g5p-suspend follow-up; not published)

- **Problem.** A 330-character emergency printk during G5P bring-up stalls expedited RCU on CPU0 (about 29 ms on the
  115200 serial console). `/sys/power/suspend_ready` could not say why the GPU refused, and answered `ready` for a
  busy GPU whose pinned firmware can never certify.
- **Changes.**
  - `drivers/drm/0028`: the readback goes to info level in three records.
  - `core/0004`: an optional admission reason in the device token.
  - `drivers/drm/0029`: G5P reason tokens, and a never-park refusal while busy.
- **Other devices.** None. G5P is J71t only. The core field is optional and other providers are unchanged (VXD has no
  reason).
- **Depends on.** `core/0002`/`0003` (suspend topic) and g5p-suspend `0023–0027`. Merge after the suspend readiness
  topic. `core/0004` lives only in g5p-suspend.
- **Device test still required.** §4.
- **CHANGELOG.** "J71t: the GPU no longer stalls RCU during warm-boot bring-up; `/sys/power/suspend_ready` names why the
  GPU refuses sleep (pinned never-park firmware)."
