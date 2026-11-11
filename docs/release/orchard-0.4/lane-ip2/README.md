# Lane IP2: integration-g's IP0 failure (cmd8 never consumed) and the fix (host only, not device-proven)

2026-11-11, Opus 5.5. No device access, no push, no GitHub edits, m1n1 tree not opened, no Apple bytes in files.
Labels: [V] verified decode or log line, [I] inferred, [P] predicted on device.

| Repo | Branch | Head | On |
|---|---|---|---|
| Linux `/src/orchard-linux-gs` (volume `linux-a9-src`) | `j71t-04/g5p-suspend` | `c5bb0ba78` | lane IP `c5d09f005` |
| Orchard `build/orchard-0.4/orchard-gs` | `j71t-04/g5p-suspend` | `25518eb` (adds `drivers/drm/0032`) | lane IP `b03bbbb` |
| Orchard integration `build/orchard-0.4/orchard` | `j71t-04/integration` | `6951976` (tree `04c3c7d`) | `b7ed084` (tag `ip2-backup-integration-b7ed084`) |

## 1. Root cause: the diff between integration-g and every good boot

The orchestrator's steer was to start from the diff. integration-e = integration-g minus `drivers/drm/0030/0031`, and
0031 only touches the sleep path. Every 0030 hunk outside the map is gated on `park_epoch`, which stays false until the
arm (the doorbells, R0 refusal and PM record). So the failure has to come from what 0030 writes at map. That is
`g5p_park_install()` plus `perf_poweron = 0`.

**Good reference.** No integration-e or opt1 cold-boot dmesg with these markers exists on the host. `flight-c/` holds
only benchmark output, and `build/opt1/device-results` has no autoboot lines. The closest is
`build/lane-c/boot-1-kernel.log` (kernel `vdm-warmport-20261108`, the same driver line and the same pinned map).

| Before release / at bring-up | good (pinned, e's map) | integration-g IP0 |
|---|---|---|
| release requests pstate | **4** (`GPUPERF poweron q=4 r1_1000=00000004`) | **1** (`perf_poweron = 0`) |
| ALIVE GPC | `state=00000004` | `state=00000001` |
| override `ctrl+0x1038/0x1040` | 400/400 | 0/0 |
| `policy+0x28` target | 4/4 | 1/1, then **2** by 10 s |
| `policy+4` sampler | 0 | 16 |
| `ctrl+0x1028` envelope | 3348 | 3851 |
| coefficient block (47 words) | absent | present |
| `meta+0x6c4`, `meta+0x700` | 0, 0 | 1, 1 |
| `ctrl+0x20` | 0 | 0 |
| cmd8 | `R74B cmd8-consumed` about 0.2 s after ALIVE | `DC timeout consumer=0 producer=1` |

**What the firmware does with g's words** (META image disassembly, `build/gpu/firmware-re/10000000.minim.dis`):

- **[V] `meta+0x6c4` turns on a main-loop routine the pinned record never runs.**
  - The per-boot init copy `0x10003ca4` moves meta words into priv, and **the copy is not linear**:
    - `priv+0x228 = meta+0x6c0` (`0x10003cd8`);
    - `priv+0x22c = meta+0x6c8` (`0x10003ce8`);
    - `priv+0x230 = meta+0x6c4` (`0x10003cf0`).
  - The main loop (`0x100106c0`) calls `0x100044f0` on every pass that has no event bits pending, when
    `priv+0x230 ≠ 0` (`0x10010808..0x10010824`).
  - integration-e leaves `meta+0x6c4 = 0`, so that routine never runs on any Linux boot except g's.
  - `0x100044f0` is a large per-context routine (counters at `policy+0x934`; calls `0x1001ef2c`, `0x1001340c`). How it
    could hold the control queue is **[I], not decoded**.
  - The second writer of `priv+0x230` (`0x1000114c`) is a second copy of the same `meta+0x6c4` word, with the same
    mapping. The two `+#560` stores in the `0x80000000` region are 64-bit stores to other structures.
- **[V] The firmware never attempted a pstate change.**
  - The setter `0x1001c88c` stores `policy+0x34 = idx` before it touches Fender (`0x1001c900`).
  - `policy+0x34` stayed 1 while the target read 2, so the firmware isn't stuck in a DVFS poll.
  - [I] (lane IP's reading of the governor, not re-decoded here): the target moves only across a park, which
    `ctrl+0x20 = 0` vetoes.
- **[V] `meta+0x700` is not in the init copy.** Its only reference in the `0x10000000` region is a store at
  `0x1001d440`.
- **[V] The sampler gate is `priv+0x228 && priv+0x22c` = `meta+0x6c0 && meta+0x6c8`** (`0x1000aaac..0x1000aad8`).
  Both are 1 in e too, so the boot sampler runs on e as well; `+0=1` at pre-bell on the good boot confirms it.
- **[V] The park itself needs none of g's words.**
  - The idle tail (`0x10009bd8`) proceeds only with `priv+0x188 ≠ 0` (`ctrl+0x20`, `0x10009bec`) and
    `policy+0x34 ≠ 0` (a powered pstate, `0x10009c0c`).
  - It then checks engines idle, rings empty, `0x10001bdc` and `0x1001ee98`, and parks at target `policy+0x28`.
  - The pinned record has `policy+0x34 = 4`.
- **[I] The same pair appears twice.** `policy+4 = 16` with `ctrl+0x20 = 0` also occurred in latency123 T2/T3 (first
  TA consumed, never started). IP0 is the same pair plus the words above.

**Conclusion.**
- [V] What broke is exactly g's map-time record: on IP0 everything else is e's.
- [I] Which word held cmd8 is not isolated statically. `meta+0x6c4` is the strongest suspect, because it is the only
  word that enables firmware code e never runs. But the pstate-1 release, the removed pin and `policy+4 = 16` at
  `ctl20 = 0` changed together.
- [V] None of these words is needed for bring-up or for the park itself. So the fix doesn't pick one. It puts the whole
  map back to e's and moves the record to the arm.

**Why `bootFirmwareAndWait` succeeds on iOS with this record [I].** iOS writes `ctrl+0x20 = 1` at init
(`fffffff006c97888`). Its firmware can therefore park and wake to apply the governor's target, and it runs the
`priv+0x230` routine in the configuration it was written for. Lane IP's "arm after bring-up" deviation was what created
the never-seen state: iOS's record with the park vetoed. The opposite deviation (B2: `ctl20 = 1` before release) parks
before Linux's first-ALIVE GPC proof. So the record can't be safe at bring-up on Linux either way. That is why it moves
to the arm.

**No-freeze note.** The orchestrator corrected the report: the iPad didn't freeze after IP0. The owner rebooted it into
iOS on purpose. This lane claims nothing about a stopped autoboot's safety.

Ghidra: this RE is on the META firmware image, which is not in the shared Ghidra project. Nothing was renamed, so
there was nothing to save.

## 2. Fix: `drivers/drm/0032` (Linux `c5bb0ba78`), smallest revert plus a reorder

- **Map = integration-e, word for word.**
  - `perf_poweron = g5p_perf_seed_q(400) = 4` again: GPC 4 at release, `policy+0x28 = 4/4`.
  - `g5p_park_install()` is gone, so no record, no `meta+0x6c4/0x700`, `policy+4 = 0` and the 3348 envelope at map.
  - `git diff 8bc223aeb -- boot.inc` over `g5p_boot_maps` shows only the three host-side latches
    (`self_park`, `self_park_armed`, `park_epoch`).
  - The `GPUPERF self-park …` map line no longer exists, so its presence on device means the wrong kernel.
- **Arm, live, only on a complete epoch.** The conditions are unchanged: ALIVE, `control_complete`, nothing failed or
  stopped. It runs at `autoboot complete` and after a successful in-boot recovery. The order is:
  1. iOS's coefficient block and filter init (the same 47 words), and `ctrl+0x1028 = 3851`, then `dma_wmb`;
  2. `policy+4 = 16`, then `dma_wmb`;
  3. `ctrl+0x20 = 1`, then a Normal-NC read-back.

  The pin (`ctrl+0x1038/0x1040 = 400`) stays, so the park hands the wake `R1+0x1004 = policy+0x28 = 4`.
  `meta+0x6c4/0x700` stay 0.
- **Why the arm writes the block and `policy+4`.**
  - [V] The wake reboots through the boot sampler. With `+0 = 1` it divides by `policy+4` (`0x1000ac28`), so
    `policy+4` must be nonzero before the first park.
  - [I] Seed 2 (pinned, `+4 = 16`, stale stamp) ran the load governor to pstate 0 and sent no ALIVE.
    `perf-envelope.h` blames the zero busy accumulators of a fresh record. That iOS's coefficient block keeps a wake off
    pstate 0 is inferred: it is the only record Apple runs through that path. 0032's commit message states it as fact;
    reword it when folding into 0030.
  - `policy+4` is written immediately before `ctrl+0x20`, so the latency123 pair exists only between two stores.
- **Fail closed.** A refused arm writes nothing. Any epoch that didn't complete is integration-e's pinned never-park
  epoch, exactly as booted.
- **Disarm** (`resume-boot` only, the firmware stopped by GS2's sleep):
  - `ctrl+0x20 = 0`;
  - the block back to pinned values (`policy+0x688 = 400`, others 0), envelope 3348;
  - `policy+4 = 0` and `policy+0 = 0`, so the retained boot's sampler takes its first-call init. That also removes the
    division GS2's resume would have hit on e's record.
- **debugfs `park 0`** now returns `-EBUSY` once the epoch is armed: a live epoch is never disarmed. `pin 0|N` is
  unchanged and is used in IP4.
- Lane IP's doorbells, R0 refusal, PM record and 0031 sleep certificate are untouched and still keyed on `park_epoch`.

## 3. Build, bundle, tests (host only; host tests are not hardware results)

- **Object.** `a9-gpu-drm.o` (W=1, LLVM, toolchain image): only GS2's five inherited `-Wunused-value`.
  checkpatch `--strict --no-signoff`: 0/0/0.
- **Export.** `export.py --base c5d09f005 --topic c5bb0ba78=drivers/drm`: "applied to c5d09f005 they reproduce
  j71t-04/g5p-suspend exactly".
  - orchard-gs `25518eb` adds `0032` and updates the `devices/j71t/device.toml` / `chips/s8003.toml` comments.
  - `tools/catalog/generate matrix`: no change.
- **Integration `6951976`.** It merges `25518eb` into `b7ed084`. The conflicts were TOML comment lines only; the
  self-park line was rewritten in each file.
- **Kernel.**
  - Command: `ORCHARD_KERNEL_TEST_SUFFIX=integration04g2 JOBS=6 scripts/orchard/build-orchard-kernel.sh
    build/orchard-0.4/orchard out-integration04g2 j71t`.
  - Result: exit 0, 560 patches, 77 modules, vermagic PASS, inherited warnings only.
  - Release `7.3.0-rc1-orchard-apple-16k-topic-integration04g2`; `Image.gz` `3298c69c…`. The Image carries the new arm
    string and no `GPUPERF self-park`.
  - `j71t.dtb` is identical to g's.
  - Log `integration/kernel-build-ip2.log`, receipt `integration/build-receipt-g2.json`.
  - `integration/README.md` has a new g2 section at the top.
- **Bundle.**
  - Script `scripts/orchard/package-orchard04g2-integration.py`. It moves g's packet, MANIFEST and DEVICE-COMMANDS to
    `integration/prev-integration-g/`.
  - It takes the kernel, modules and a fresh initrd (stable USB identity and compiled J71t DT asserted). Userspace and
    runner are g's, byte for byte (asserted).
  - Path: **`build/orchard-0.4/integration/orchard-04-integration-g2.tar.gz`** (23.5 MB).
  - **SHA256 `13336e113b20…`.** The tarball, the `.sha256` file
    and the receipt's `archive_sha256` agree.
  - Packet MANIFEST: orchard `6951976`, entry `orchard-04-integration-g2`.
- **Orchard suites** (macOS venv, `PYTHONPATH=<checkout>/src`). In both, the failure names are identical to lane
  IP's:
  - orchard-gs `25518eb`: 754 tests, 7 failures, 1 error, 1 skip (`ip2-orchard-gs-tests.log` (not published));
  - integration `6951976`: 773 tests, 7 failures, 1 error, 3 skips
    (`ip2-orchard-integration-tests.log` (not published)).
- **GPU ms/frame, busy % and fps: unmeasured** (no device access). IP4 measures them.

## 4. Device flight

`DEVICE-COMMANDS-ip2.txt` (not published) is prepended to `integration/DEVICE-COMMANDS.txt` in place of lane
IP's block. g's other blocks follow, renamed to g2.

**IP0 must show, in order [P].** These are the fields that must match. Every format string was checked in the g2
Image; the values are the pinned boot's (`build/lane-c/boot-1-kernel.log`). Times, `owner=`, `case=` and the readback
line shapes may vary.

```
GPUPERF poweron q=4 policy28=4/4 policy0=0 policy4=0 ...
GPUPERF boot pin=400 ... limits=3348/400/400 ovr=400/400 ... policy4=0 ... q=4 ... policy28=4/4 ...
GPUPERF poweron q=4 r1_1000=00000004 ... ret=0          (g printed "R74E power ... raw=00000001" here)
R74E ALIVE submit ... state=00000004 after=00000004 ret=0 ... power_abort=0 submitted=1
R74B cmd8-consumed consumer=1 producer=1 ...
autoboot phase=control-wait result=0
autoboot complete: GPU up
G5P self-park armed why=autoboot ctl20=1 policy4=16 envelope=3851 pin=400/400 end=park
```

It must show no `GPUPERF self-park` line. `g5p_self_park` should read `self_park=1 armed=1 park_epoch=1 ctl20=1`,
`ovr=400/400`, `policy0=1 sample_ms=16 … target=4`.

**Risk moves to IP1/IP2 [I].**
- **Live block write.** The arm writes iOS's filter-init words into a governor that has run on zeros since boot.
- **Wake path.** IP2's wake is the first time a woken boot sampler sees an iOS-coefficient record with the pin. A
  hang there with GPC 0 and no events is the seed-2 signature (S3).

**If IP2 hangs**, the next step is an iOS probe: a policy-record dump across one park/wake on iOS
(`scripts/gpu/apple-idle-power-probe.sh` U1/U4: `policy+0/+4/+0x28/+0x34/+0x8f8` and `ctrl+0x20` before and after an
idle gap). Not another variant.

**Follow-up for publication.** 0032 corrects 0030 before either is published. At publish time fold it into 0030 and
rewrite 0030's message ("install iOS's policy record … the release powers the GPC on at 1" no longer holds). 0031 is
unaffected (different file).

**PR text (draft, for the orchard g5p-suspend PR).**
- Problem: 0030's map-time record kept the firmware from consuming the bring-up control command.
- Change: pinned bring-up; the park's record is armed live once the epoch is complete.
- Other devices: none (G5P is J71t-only).
- Dependencies: on top of 0030/0031.
- Device test: the IP0–IP8 block above.
- Proposed CHANGELOG line: unchanged from lane IP.
