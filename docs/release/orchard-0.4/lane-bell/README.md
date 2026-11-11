# Lane BELL: ring a parked firmware without the GPC settle wait (host only, not device-proven)

2026-11-11, Opus 5.5. No device access, no push, no GitHub edits, m1n1 tree not opened, no Apple bytes in files.
Labels: [V] verified (decode, source or log line), [I] inferred, [P] predicted on device.

| Repo | Branch | Head | On |
|---|---|---|---|
| Linux `/src/orchard-linux-gs` (volume `linux-a9-src`) | `j71t-04/g5p-suspend` | `2c299bb18` | lane IP2 `c5bb0ba78` |
| Orchard `build/orchard-0.4/orchard-gs` | `j71t-04/g5p-suspend` | `4d2d4be` (adds `drivers/drm/0033`) | lane IP2 `25518eb` |
| Orchard integration `build/orchard-0.4/lane-bell/orchard-h3` | `j71t-04/bell-integration-h3` | `49dc3c9` (tree `e6ad474`) | integration-i `fac8ee2` (= h2 `49848ce` + AMC `b52d443`) |

## 1. The problem and why the settle is pure waste [V]

On h2 the firmware parks between frames (FLIGHT-H2). Each park-epoch doorbell still ran integration-e's settle: after
`R1+0x14 = 7` it re-read `R1+0x1000` every 10 µs for up to 2 ms, waiting for a settled powered GPC. Only then did it
ring at any nibble. That added about 400 µs of host time per job (`bell_ns`/jobs 394–410 µs, against 1–2 µs without
park).

**A parked GPC comes on only after the bell, so the wait always runs to its 2 ms end.** h2's netconsole
(`build/orchard-0.4/integration/flight-h2/netconsole.log`) shows it:
- 455 `RENDER-V3 dc-kick … did=rang-parked … gpc=00000000 settle=185|186`: the full 2 ms of reads;
- the GPC was still at 0 every time;
- the firmware woke on every one of those bells. IP3 passed 50/50 and every bind/close completed.

So h2 has already rung a parked firmware at nibble 0 455 times. The settle bought nothing there.

That holds for the DC kicks. For the per-job wake110 publish it is [I]: the log has no wake lines, only the 400 µs
average. That average is consistent with the full 2 ms on the jobs that found the firmware parked.

**Apple's order (Ghidra, `AGXMetaFirmware_submitDeviceControl` `fffffff006ca05d4`, re-read for this lane):**
1. `dmb`;
2. Fender `+0x80` (`R1+0x14 = 7` plus read-back);
3. one `+0x18` nibble read;
4. at nibble 0, only the `+0x70` / `+0x78` / `+0x90` (`+0x88`) read-backs. `forcePowerCycleAndReboot` runs only with
   `platform+0x510` bit 0 clear, and J71t has it set;
5. `R0+0xb00 = 0x10`.

There is no wait loop.

## 2. The change: `drivers/drm/0033` (Linux `2c299bb18`, 17+/9−, two files)

In a park epoch every doorbell reads the GPC once and rings. Each site takes one `park_epoch` snapshot and uses it for
both the settle skip and `g5p_park_may_ring()`.

| Site | File | Change |
|---|---|---|
| r74f bells (`g5p_r74f_ring`, event_lock held, IRQs off) | `boot-r74f.inc` | perf60 settle block runs only `if (!park)` |
| DC kicks (`g5p_rv3_dc_kick`: bind, close, park, spares, kexec quiesce) | `drm-render-v3.inc` | settle loop `while (!park && …)`; its log now prints `settle=0` in park epochs |
| wake110 per-job publish (render `g5p_rv3_wake`, compute `g5p_cu_wake`, the shared `g5p_rv3_wk_r1`) | `drm-render-v3.inc` | `g5p_rv3_wk_r1` returns the single raw GPC read in a park epoch; `render-user-wake.h` (host-suite header) untouched |
| `g5p_prepare_kick` (DC, DC re-kick, RENDER-USER-unbind) | `kick.inc` | **none**: it already reads the GPC once |

**Kept as is:**
- **The fail-closed refusal.** A GPC that isn't on rings only if `R1+0 ≠ 0`. A parked wrapper reads
  `R1+0[30:29] = 11`, and the unpark handshake writes `0x40000000`, so neither is 0.
- **Never-park epochs.** That covers before the arm, an arm that was refused, and after resume's disarm. Every settle
  and value there is unchanged.

**Does anything need the settled value? [V] No.**
- The value after the settle is used only for the ring decision and for logs: `bell_state`, `wk_gpc`, and the
  `dc-kick gpc=` field.
- The r74e reactivation and ALIVE-deferred paths run only on `-EHOSTDOWN`. A park epoch doesn't return that (lane IP).
- The other two timed loops in this area are not doorbell paths:
  - the fault R0 read at `drm-render-v3.inc:2763`, which park epochs refuse before any bus access;
  - the dc-probe diagnostics in `lifecycle.inc`.

**Snapshot mismatch.** `g5p_rv3_wk_r1` reads `park_epoch` itself, while `g5p_wk_ring()` uses the caller's `io.park`.
A live epoch only moves from never-park to park, so the only possible mismatch is this: the settle is skipped while
`io.park` is still false. Then the ring refuses an off GPC (`SKIP_GPC`), which fails closed.

**`bell_ns` keeps its meaning.** It is still `wk_start_ns` → `wk_done_ns` per engine (`drm-render-v3.inc:3496`): the
host time spent in the publish-time doorbell decision, under event_lock. Only the 2 ms wait inside it is gone.

## 3. Build, bundle, tests (host only; host tests are not hardware results)

**Kernel commit:**
- checkpatch `--strict --no-signoff`: 0/0/0.
- Export: `export.py --base c5bb0ba78 --topic 2c299bb18=drivers/drm`. Result: "applied to c5bb0ba78 they reproduce
  j71t-04/g5p-suspend exactly".
- orchard-gs `4d2d4be` adds 0033 and one comment line in `devices/j71t/device.toml`.
- `tools/catalog/generate matrix`: no change.

**Integration-h3 `49dc3c9`:**
- It merges `4d2d4be` into integration-i `fac8ee2`. The only conflict was the `device.toml` comment block; it was
  resolved to i's text plus one G5P line.
- `git diff fac8ee2`: 0033 and that one line.

**Kernel build:**
- Command: `ORCHARD_KERNEL_TEST_SUFFIX=integration04h3 JOBS=6 scripts/orchard/build-orchard-kernel.sh
  build/orchard-0.4/lane-bell/orchard-h3 out-integration04h3 j71t`.
- Result: exit 0, 77 modules, vermagic PASS. Log: `build/orchard-0.4/lane-bell/kernel-build-h3.log`.
- Warnings: only GS2's five inherited `-Wunused-value` (`drm-render-v3.inc:1622/1745/3212/3219/3221`). None is on a
  changed line. integration-i's incremental build didn't recompile this driver, so they don't appear in its log.
- Release `7.3.0-rc1-orchard-apple-16k-topic-integration04h3`. `j71t.dtb` is identical to integration-i's
  (`79f791d1…`).

**Bundle:**
- Script: `scripts/orchard/package-orchard04h3-integration.py`. Base is the integration-i bundle; the script writes
  only `build/orchard-0.4/integration-h3/`.
- It takes the new kernel, modules and a fresh initrd. The stable USB identity and the compiled J71t DT are asserted.
- Also asserted:
  - h2's SoC node and i's AMC node are present;
  - the arm format string is in the Image, and `GPUPERF self-park` is not;
  - userspace, runner and tools are i's byte for byte (= h2's userspace).
- **`build/orchard-0.4/integration-h3/orchard-04-integration-h3.tar.gz`** (23.5 MB).
- **SHA256 `47419b2e68d2…`.** The `.sha256` file and the receipt
  agree.
- The bundle's `DEVICE-COMMANDS.txt` is this lane's block followed by integration-i's, renamed to h3.

**Orchard suites** (macOS venv, `PYTHONPATH=<checkout>/src`):
- integration-h3 `49dc3c9`: 773 tests, 7 failures, 1 error, 3 skips. That is the baseline, and the FAIL/ERROR names
  are identical to `lane-ip2/ip2-orchard-integration-tests.log` (`bell-orchard-h3-tests.log` (not published)).
- orchard-gs `4d2d4be`: 754 tests, 7 failures, 1 error, 1 skip, names identical to IP2's
  (`bell-orchard-gs-tests.log` (not published)).
- **Run the suites one at a time.** My first attempt ran both at once, and both stalled for over 30 minutes in
  `test_platforms_index…test_the_index_names_every_file…`, spawning short python children. I stopped them and reran
  each alone; each finished in about 5 minutes.

**GPU ms/frame, busy % and fps: unmeasured** (no device access). The check below measures them.

## 4. Device check (`DEVICE-COMMANDS-bell.txt` (not published), first block of the bundle's file)

It is a day flight and hang-class. Warm hop from the running h2 into h3. The DT differs from h2's (i's AMC node), so
expect the legacy loader and make the first hop with menu Restart. Then i's S2 readback; state 12 is required.

| Step | What | Pass |
|---|---|---|
| B0 | warm keys | `autoboot complete: GPU up`; `G5P self-park armed why=autoboot ctl20=1 …`; `park_epoch=1` |
| B1 | one glmark2 build run right after a 5 s idle park | rc 0, no S3; `dc-kick … did=rang-parked gpc=00000000 settle=0` |
| B2 | glmark2 build fullscreen ×3, labwc G5P environment (`/opt/orchard/g5p`), per-job `g5p_gpu_stats` | **`bell` back near 0 µs/job** (h2: 394–410), fps up from h2's 340–365, no S3 |
| B3 | 20 park/unpark cycles (IP3-style) | 20/20 rc 0, no S3 line, parks between runs |

**Predictions [P]:**
- `bell` 1–2 µs/job.
- The settle ran *before* the bell, and a parked GPC powers on only *after* it. So the 2 ms was added latency, not
  overlap with the wake.
- `ta_wait` starts at `ta_pub_ns`, which is stamped before the producer store and the bell
  (`drm-render-v3.inc:1606`). So the settle also sat inside TA wait. Expect TA wait to drop by about the bell's
  0.4 ms (h2 1544–1659 → about 1150–1250 µs), and fps to rise.
- The residual over opt1's 865 µs is the real firmware wake: GPC power-on of about 550 µs plus the firmware's
  restart. That is fix candidate 2 (several frames in flight), not this patch.
- **B0 attribution.** No warm boot with the live arm has flown yet: h2 flew IP0–IP4 from a cold boot, and IP5 is
  pending. 0033 does nothing before the arm, so a failure at or before the arm belongs to the warm arm or to the
  never-flown AMC topic.

**Failure signatures and next step:**
- **B-S1:** the first job after a park never starts its TA, i.e. a bell rung at nibble 0 was lost. Stop.
- **B-S2:** `did=skip-gpc` in a park epoch: a dead wrapper. Stop.
- After either one, the next step is the iOS park/wake probe (`apple-idle-power-probe.sh` U1/U4), not another variant.

## 5. Draft PR text (orchard g5p-suspend PR)

- **Problem:** in park epochs every doorbell waited up to 2 ms for a GPC that a parked firmware powers on only after
  the doorbell. That cost about 0.4 ms of host CPU per job.
- **Change:** park epochs read the GPC once and ring, in Apple's `submitDeviceControl` order. The `R1+0 == 0` refusal
  is kept.
- **Other devices:** none (G5P is J71t-only).
- **Dependencies:** on top of 0030–0032. Merge order: after 0032.
- **Device test:** B0–B3 above.
- **Proposed CHANGELOG line:** none of its own; it is covered by lane IP's self-park line.
- **Publication:** fold 0033 with 0032 into 0030 when they are folded.
