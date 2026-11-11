# perf60-fillrate: why full-panel 3D runs at ~70–100 Mpx/s and every TA costs ~8 ms

2026-11-02, research sub-agent for `perf60.md` (not published). Host only: no device access. Labels: **[V]** read in a
named file, log line or source; **[I]** inference; **[O]** open. Kernel `a9/perf60-fill` = `a9/release7@802a3d4fc4` +
one commit (§4). Nothing here needs DFU.

## 0. Answers

1. **Our 3D register image matches Apple's one-sample image except in one bit, and that bit disables tile skipping.**
   - The 3D template's ISP_CTL (W3D+0x3c0 → CR `0xf38`) is `0x0023000f` [V `core/render-user-template.h`]. Apple's 1×
     value is `0x0021000f`: Apple sets bit 17 (`PROCESS_EMPTY_TILES`) only for a 4× resolve (record+0x640 → D6ad)
     [V `msaa.md` "ISP_CTL bit 17", `core/render-user-msaa.h`].
   - Linux forced bit 17 on for **every** pass in `0e05f993cf`, so that CLEAR passes write tiles that have no geometry
     [V `display101-empty-tiles.md`]. That doc says the production form is a per-pass flag from Mesa. The flag was
     never built.
   - Upstream pvr sets it only when a colour attachment has loadOp CLEAR [V `pvr_arch_cmd_buffer.c:10086-10112` in
     `build/third_party/mesa-a9-hyprland-src`]. Our ICD has no such path (`g5p_drm_render.c` leaves
     `background_texture = 0`, and has no clear/load flag) [V].
   - **Consequence [I, strong]:** every LOAD pass runs the background load and the end-of-tile store on all 3072 tiles
     (1536×2048), even when only a gears window is damaged. With bit 17 clear, a tile whose region header holds no
     primitive is skipped and its memory is untouched (display101 saw exactly that). That is the hardware's native tile
     skip: **no render rect or region-header pruning is needed.** Whether Hyprland gains depends on whether the tiler
     bins by the scissor or only by primitive bounds (fixture `fill_load_scissor` vs `fill_load_small`).
2. **The other 3D words are Apple's.** The six per-core words W108..130 (`0x3c3`), W3c4 `0x408`, W3c8 `8`, W3cc `0xf8`
   and W6b0 come from the hash-pinned r22 importer's template, or from the importer's width table `5942678`
   [V template, `render-uapi.md` TYPED_V2]. ISP_MTILE_SIZE (W3a0 = Rbc) and ISP_RGN (Wa8) use the derivation shared
   with Mesa pvr (`0xc0010` for 1536×2048) [V `render-uapi.md` table]. **No pipe/cluster/USC/ISP/PBE count differs** [I].
   - ISP_CTL fields above bit 17 do not follow the public Rogue names on A9: bit 21 is the pixel-output/AA shift
     [V `render-user-msaa.h`]. The "PIPE_ENABLE = 0" reading is the same as Apple's word and means nothing new.
   - The A9 has 6 clusters in 2 cluster groups: 2 ISPs, 1 IPP [V `dsx-nx78` §0]. No host-written cluster mask has been
     found. Firmware Rascal/Dust islanding is off on our boot, which leaves us *more* powered, not less [V/I
     `dsx-nx20-trigger-power.md` §2.3]. That policy state 2 gates clusters as well as the clock: **no evidence [O]**.
     pstate 1 (340 MHz) vs iOS's P4 (723 MHz) can explain at most ×2.1.
3. **The per-tile cost looks like memory latency: ~14 µs per tile, one DRAM round trip per line [I].**
   - Linear fit over tonight's log: gears 3D 6.2 ms for ~361 tiles [I: the window is "about 300×300 at scale 2", taken as 600×600 px], Hyprland 44.8 ms for 3072 tiles. That gives
     ≈14 µs per tile (≈4800 cycles at 340 MHz) plus a fixed ~1.5 ms [V log, §1].
   - A LOAD tile moves 4 KB in and 4 KB out = 128 lines of 64 B: 14 µs / 128 ≈ 110 ns per line. That is one DRAM round
     trip per line with no overlap.
   - The same rate holds for Hyprland's composite and labwc's trivial blit [V perf60.md]. So the bound is per pixel or
     per line, not per instruction.
   - **Leading suspect: the leaf attributes `0xc` (CC + SLC bypass) on every VM_BIND map** (render targets, textures)
     [V `drm-vm.inc` `g5p_pte_attrs()`].
   - iOS's host-buffer path is believed to pass `0xc` as well [I, `dsx-nx3-slc-config.md` §2.6, from the kext's
     range-attribute table `0x59426c8`; no iOS GART walk of a render target exists]. So this may not differ from iOS.
     The A/B decides it.
   - The knob already exists in release7 (`pte_variant`, 0600, new maps only) and **has never been flown** [V: no
     log under `build/gpu/latency123*` sets it].
4. **The TA's fixed ~8.5 ms is in the firmware's dispatch path, not in the TA itself [V/I].**
   - Every client shows the same TA time: publish → TA event 8.7 ms median for Hyprland (n=167), 8.3 for quickshell
     and gears (§1) [V]. The size of the TA's geometry does not matter.
   - L123 lines on an earlier desktop boot: the ring is **consumed 2–4 ms after the publish**, the TA is done at
     8–10 ms, and the 3D is consumed 2 ms after its own publish [V `logs/vpds/dmesg-r2.txt`, e.g.
     `ta ... pub=0 cons=3 ... done=9 td ... pub=9 cons=11`].
   - For jobs ≥ 2 the host rings no doorbell (`kick=0`), and the firmware finds work by polling RAM [V
     `g5p_rv3_publish_ta`, log `RENDER publish ... kick=0`]. The firmware sees its own root/shared lines only after a
     coherent host read (`g5p_rv3_fw_touch`, latency123) [V STATUS §3.2]. That read runs once per wait sample, every
     1–2 ms (`usleep_range(1000, 2000)` in `g5p_l123_pause`) [V].
   - **Hypothesis [I]:** each firmware wait on its own line lasts until the next host touch. TA ≈ 4–5 sample periods;
     the 3D's consume ≈ 1–2. Test: `perf60_poll_us`.
   - The doorbell itself is settled: wake110–112 were NULL [V `latency115` §"What remains"]. Not revisited.
5. **Serialization is host-imposed [V], and overlap is not the first lever [I].**
   - `g5p_rv3_td_why` refuses to publish the 3D until the TA has retired (bit 0), but the 3D record already carries
     the firmware dependency word `{4, TA stamp+4, seq}` (bits 7–9) [V code, `apple-3d-fragment-contract-exact.md`].
     iOS publishes the TA and then the 3D back to back [V `ds-sprint-2-ios-diff.md` row 6].
   - So an early 3D publish within one job is Apple's order. It would save the TA-event → 3D-publish → 3D-consume
     latency (~3 ms per job).
   - Overlapping the next job's TA with this job's 3D also needs a second parameter buffer (PM state) per context, or
     the TA of job N+1 overwrites what the 3D of job N reads [I].
   - Neither is built tonight. The r37/r49 pair runs predate a working TA, and the 3D at 45 ms dominates anyway.

## 1. Tonight's timeline (`build/gpu/perf60/gears-nocm-dmesg.txt`, medians, ms) [V]

| client (slots) | n | TA publish → TA event | TA event → 3D publish | 3D publish → 3D event | 3D event → done | done → next publish |
|---|---|---|---|---|---|---|
| Hyprland (8/7) | 167 | 8.7 | 0.92 | **44.8** | 1.08 | 3.89 |
| quickshell (10/9) | 47 | 8.3 | 0.76 | 17.4 | 0.95 | 0.45 |
| gears (12/11) | 18 | 8.3 | 1.13 | 6.2 | 1.17 | 0.09 |

Per Hyprland job: ~59 ms, of which the 3D is 45 ms, the TA 8.7 ms and host edges ~2–6 ms. At ~14 full-panel jobs/s,
gears queues behind them (orchestrator's addendum).

## 2. Our 3D vs Apple's, item by item

| item | ours | Apple | differs? | plausible cost | flip |
|---|---|---|---|---|---|
| ISP_CTL bit 17 (process empty tiles) | 1 on every pass | 1 only on a 4× resolve | **yes** [V] | every LOAD pass pays all 3072 tiles; a small-damage frame pays ∝ damage | `perf60_empty_tiles=1` (measurement); proper: a UAPI pass flag that Mesa sets iff a colour attachment CLEARs or resolves |
| ISP_CTL other bits, W3c4/W3c8/W3cc, W108..130 (6 cores), W6b0 | importer template | same | no [V] | – | – |
| ISP_MTILE_SIZE / ISP_RGN | derived, `0xc0010` / mx·my·5 | same derivation | no [I] | – | – |
| leaf attrs of RTs and textures | `0xc` (CC + SLC bypass) | `0xc` believed | unknown [I] | if CC/bypass serialize the PBE and texture lines: the whole ×10 | `pte_variant` 1 (CC only), 2 (bypass only), 3 (0) |
| background LOAD program | ICD's | captured `usc=116B`, `bgrnd0 0x28c0/0x2840` (`ios-capture-bundle/…/parsed-v2/load.json`) | not compared byte for byte [O] | a per-tile wait would show as `fill_solid` ≫ `fill_clear` | – |
| end-of-tile program | userspace PBE emit | captured (mrt2/mrt4 decoded) | [O] | – | – |
| pstate / clock | P1 340 MHz | P4 723 MHz under load | yes [V] | ×2.1 at most | `nopatch.md` lane (not here) |
| cluster gating by policy state 2 | – | – | no evidence [O] | – | – |

Not usable: the stress capture's `b3d_w.hex` is a different block layout, not a filled W3D (its A block reads zero).
It is not cited as Apple's register image.

## 3. What each fixture rung isolates

`tools/mesa-a9-hyprland-gpu/fill-ladder.c`: 1536×2048 RGBA8, 20 timed frames per rung, each one pass ended by
`glFinish`, and the target read back once and checked exactly.

| rung | per tile | compared with | tells |
|---|---|---|---|
| `fill_clear` | background clear + store | – | the store cost and the per-tile floor |
| `fill_solid` | background **load** + store, no texture | `fill_clear` | the cost of the background-load program |
| `fill_blit` | load + texture read + store | `fill_solid` | the cost of the texture fetch (Hyprland's composite) |
| `fill_load_small` | 4 tiles with geometry | `fill_solid` | tile skipping with `perf60_empty_tiles=1` |
| `fill_load_scissor` | full-screen triangle, 64×64 scissor | `fill_load_small` | whether the tiler bins by the scissor (Hyprland's damage case) |

## 4. DEVICE-READY

### Artifacts

- **Kernel** `a9/perf60-fill@b2d7c04e83` (public fork; one commit on `a9/release7@802a3d4fc4`;
  `build/gpu/perf60/perf60-knobs.patch`). Release `7.3.0-rc1-perf60-gb2d7c04e83b5`. The config is byte-identical to
  release7's. The DTBs (stock OPPs), the initramfs and the cmdline are release7's packaged ones; only
  `linux_a9.entry` differs.
  - Entry `perf60-b2d7c04e83`. Payload `build/boot/m1n1-linux-perf60-b2d7c04e83.bin`, sha256
    `ab5bb08841eb…` (`build/gpu/perf60/payload.sha256`).
  - Entry files: `build/gpu/perf60/perf60-b2d7c04e83-entry/` (`entry.sha256`).
  - Build/package script: `scripts/gpu/perf60-build.sh build|package|restore`.
- **Fixture overlay** `build/gpu/perf60/perf60-fixture.tar.gz`
  `e707d5d5a4d3…`. It unpacks over `/tmp/qs` and adds two files to the
  `qtpass` package already there:
  - `hypr-s2/integ-a9/a9-mesa/bin/fill-ladder`
    `0514f94745ee…` (a plain EGL/GLES client, so it runs on the
    package's ICD `3f937b1c`; offline over the fake node: 5/5 rungs, 0 refusals,
    `build/gpu/perf60/fill-ladder-offline.log`);
  - `hypr-s2/perf60-ab-device.sh` `62cfc7670b00…`. One ladder run per rung, between
    `PERF60-RUNG begin/end <arm> <rung>` kmsg markers. Every rung reuses the same spare slot pair, so the summary splits
    the kernel lines by these markers..
- **Summary**: `python3 -B -I scripts/gpu/perf60-summary.py <pulled dir>`.

### Knobs (all 0600, read at each job, default = production)

| knob | kernel | values |
|---|---|---|
| `perf60_empty_tiles` | perf60 | 0 production (bit 17 on every pass); 1 Apple's 1× form (bit 17 only on a resolve). CLEAR passes then leave tiles that have no geometry stale |
| `perf60_poll_us` | perf60 | 0 production (1000–2000 µs between RAM samples); N = 50..5000 |
| `perf60_log` | perf60 | one `RENDER-P60` line per job, in µs |
| `pte_variant` | release7 and perf60 | leaf attrs of **new** VM_BIND maps: 0 `0xc` (production), 1 `0x4` CC only, 2 `0x8` SLC bypass only, 3 `0x0` |
| `lat123_log` | release7 and perf60 | one `RENDER-L123` line per job, in ms |

### Commands (`SSH=scripts/omarchy/ssh.sh`, `P=/sys/module/a9_gpu_drm/parameters`)

Before each round: close gears and leave the screen alone, so that Hyprland stays idle and its jobs do not queue in
front of the fixture's. The kernel's per-slot lines are immune to queueing anyway; the fixture's wall time is not.

**Round 0: live release7, no hop.** Answers the memory-attribute question tonight.
*(Device/host command block omitted; it targets the private workspace.)*
Around 5 arms × 5 rungs × ~2–5 s. `pte_variant` only affects maps created while it is set: the fixture's own buffers,
plus any buffer Hyprland allocates during the arm (the script restores 0 after each arm). The fixture is a new
process, so its ICD's pre-bound arena is mapped under the arm's value as well. Hyprland buffers created during a
`pte2`/`pte3` arm (no CC) can show garbage on the panel until they are reallocated. That is a visual effect, not a
fault.

**Round 1: warm hop to perf60.** This is `release7-device.sh rollback-r6`'s sequence with the perf60 payload: stage
the running entry, quiesce the GPU, kexec. Do not use `release7-device.sh desk`, because it hops to release7 itself.
`build/gpu/perf60/entries.env` has the release6/7-form identity for any runner that wants `ENTRIES_ENV`.
*(Device/host command block omitted; it targets the private workspace.)*
**Round 2: the desktop itself**, with the winning knobs set live, then the perf60.md baseline (`es2gears_wayland`
under Hyprland, FPS, plus `dmesg | grep RENDER-P60` for 10 s):
*(Device/host command block omitted; it targets the private workspace.)*
With `perf60_empty_tiles=1`, Hyprland CLEAR passes leave tiles without geometry stale. Stale-looking areas on the
panel are that, not a fault. Revert with `echo 0`.

### How to read each knob

- **`pte_variant` (round 0):** compare `fill_clear`/`fill_solid`/`fill_blit` `us_per_tile` and P60/L123 `td`.
  - If variant 1 or 3 is ≥ 2× faster, memory attributes are the fill-rate floor. The proper fix is then per-range
    attributes as Apple's `installRangePTEs` does: render targets and textures without SLC bypass, plus cache
    maintenance for CPU-written BOs.
  - A pixel FAIL under 1/2/3 with a faster time is a coherency side effect (CPU-cached readback or uploads without
    CC), not a render bug. Record it and judge the time.
  - No change: memory attributes are ruled out, and the per-tile floor is in the USC/PBE programs or the clock.
- **`fill_clear` vs `fill_solid` vs `fill_blit` (any arm):**
  - `solid ≫ clear`: the background-load program is the cost. Compare it word for word with the captured `load.json`
    program.
  - `blit ≫ solid`: the texture fetch is the cost (texture attributes/layout).
  - All equal: a fixed per-tile cost (EOT/PBE store, or the tile loop itself).
- **`perf60_empty_tiles=1` (round 1):**
  - `fill_clear` must FAIL with most pixels stale. That proves the knob reaches ISP_CTL bit 17. P60 `w3c0=0021000f`.
  - `fill_load_small` must PASS (outside the rect untouched) with its `td` collapsing towards the fixed ~1.5 ms. That
    is tile skip working.
  - `fill_load_scissor`: as fast as `small` means the tiler bins by the scissor, and Hyprland's damage passes gain
    directly. As slow as `solid` means it bins by primitive bounds only, and Hyprland would need damage-clipped
    geometry (it draws whole-surface quads under a scissor).
- **`perf60_poll_us` (round 1):** P60 `ta_ev` and `td_cons`.
  - If `ta_ev` falls from ~8.5 ms towards ~2 ms at 200/100 µs, the TA cost is the host-touch quantization. The proper
    fix is then the firmware's own cache maintenance (latency123's open item: `policy+0x34` / the coefficient block),
    not faster polling.
  - Watch `touch` µs/sample: the CPU price of the interim touch.
  - No change: the TA time is firmware-internal (tick-bound). The next lever is the early 3D publish (§0.5).
- **Round 2:** gears FPS, and Hyprland `td` per job, against the 2.2–2.6 FPS / 44.8 ms baseline.

### Failure signatures

- A `RENDER-V3 terminal`, `fault`, `GPU-RECOVER` or `refused` line in an arm's `dmesg.txt`: stop. Report the arm and
  the line. Recovery (`render_user_recover`) or a warm hop to release7 brings the desktop back.
- A rung timeout (30 s): the arm continues only on a pass. The ladder stops on a timeout and the script restores the
  knobs.

## 5. Proper follow-ups (not done tonight)

1. **Tile skip, the proper way:** kernel side built (§7). The Mesa side is specified in §7.3, not written.
   - How Apple's 1× CLEAR passes write empty tiles without bit 17 is **[O]**: display101 shows they do not with our TA
     state. Upstream pvr clears either through the background object with bit 17, or with an index-list clear
     rectangle (real geometry, so no tile is empty; `pvr_arch_cmd_buffer.c:3645-3656`). Apple may do the latter.
2. **Memory attributes per range**, if round 0 shows a gain (Apple's per-range table `0x59426c8`).
3. **Early 3D publish** within a job (Apple's order, firmware dependency word), then a second PM context for TA/3D
   overlap across jobs.
4. Rate-limit the per-job log lines in production (perf60.md).

## 6. Build record

- `a9/perf60-fill@b2d7c04e83b5` (not pushed; the orchestrator syncs it). checkpatch: 0 errors (the warnings are only
  MAINTAINERS and the From address). The build has no new warnings.
- The volume had ~5 GB free, so the build borrowed `/src/wt/release7` with the branch checked out. `restore` ran
  `make clean` and switched it back to `a9/release7@802a3d4fc4` (clean).
- Release `7.3.0-rc1-perf60-gb2d7c04e83b5`. The config is byte-identical to `build/release/release7/config`.
- The package checks passed: cmdline, entry cmdline, initramfs and dtb are all equal to release7's. The image has the
  markers `perf60_empty_tiles`, `perf60_poll_us`, `perf60_log`, `pte_variant`, `lat123_log`, `render_user_recover`
  and `boot_alive_settle_us`.
- Payload `build/boot/m1n1-linux-perf60-b2d7c04e83.bin`:
  **`ab5bb08841eb…`**.
- Entry `perf60-b2d7c04e83` (`build/gpu/perf60/perf60-b2d7c04e83-entry/`):
  - `Image.gz` `f62ed1b0…`
  - `dtb` `40ee1e67…`
  - `initramfs.gz` `de6b2f70…`
  - `cmdline` `ed4ba922…`
  - full list in `build/gpu/perf60/entry.sha256`.
- Patch: `build/gpu/perf60/perf60-knobs.patch`.

## 7. The proper empty-tile fix: the per-pass contract (2026-11-02, built, default off)

Built on top of `a9/perf60-fill`, for when round 1 confirms the empty-tile cost.

### 7.1 Contract (UAPI, `include/uapi/drm/apple_g5p_drm.h`)

- `drm_g5p_render_pass_v3.flags` takes the `pad` slot at @508. An anonymous union keeps the name `pad`, so old sources
  still build.
- `DRM_G5P_RENDER_PASS_SKIP_EMPTY_TILES` (bit 0) means: no attachment of this pass changes a tile that holds no
  primitive. In detail:
  - the colour background LOADs (or is DONT_CARE);
  - no colour or depth/stencil aspect is cleared and then stored;
  - the pass does not resolve.
- The flag means "may skip", never "must process". So an old ICD (flag 0) keeps today's behaviour, and the kernel may
  ignore the flag: the results are the same either way, only the cost differs.
- `DRM_G5P_CAP_RENDER_SKIP_EMPTY_TILES` (bit 32, reported with TYPED_V3) says the kernel accepts the flag. Unknown
  flag bits are EINVAL. Bit 32 is free on every lane (compute uses 30, msaa/clock 31).

### 7.2 Kernel: `a9/perf60-empty@06ef780212` = `a9/perf60-fill` + one commit

- The 3D template's ISP_CTL is now Apple's one-sample `0x0021000f`. The display101 forcing is gone from the template.
- At submit, `g5p_ru_process_empty()` (`render-user-msaa.h`, pure, shared with the host test) decides bit 17 for
  every profile, applied by `g5p_ru_fill_empty_tiles()`:

  | case | bit 17 |
  |---|---|
  | 4× resolve | set, always (Apple's D6ad rule) |
  | `perf60_empty_tiles=1` (measurement override) | clear |
  | TYPED_V3 pass with `SKIP_EMPTY_TILES` and `render_user_skip_empty_tiles=Y` (0600, read at each submit, **default N**) | clear |
  | everything else (all of today's passes) | set |

- **Default-safe:** with the gate at N, every pass's W is byte for byte today's.
  - `test_msaa` builds W through the same final step: 859 checks, 0 failures.
  - The new `test_empty_tiles` rule table covers all ten cases above, including that the template is `0x0021000f`.
  - Edit: `scripts/gpu/msaa-host/test_msaa.c` (workspace).
- **Gates:** the full release7 `check` on `06ef780212` passes (`build/gpu/perf60/rel7check.log`, rc=0):
  - desk-next (faultiso, latency101, audit, mrt1, multiclient2, tahang1, mcfold2): pass.
  - msaa: 859/0; RT oracle 67,851,861 leaf runs, 0 mismatches; audit RAM-only before publication.
  - The release tuple's parameters are all present.
  - checkpatch: 0 errors (signature-form warnings and one style check).
- Compile: the driver builds without warnings. The full image comes with §7.4's combined build.

### 7.3 Mesa side: specified, **not written by this lane**

The ICD lives in `src/imagination/vulkan/g5p`. The Mesa tree's `AGENTS.md` lists `src/imagination` as a directory that
agents must not change (Imagination's contribution policy, `src/imagination/README.md#contribution-policy`), so this
lane did not edit it. An empty branch is ready: `g5p-perf60-empty` at `g5p-hypr-s1fix@002a9ff0e4e`, worktree
`build/third_party/mesa-a9-perf60-src`, no commits. Whoever owns the ICD needs these four changes:

1. `a9/g5p_typed_v3.h`:
   - `__u32 pad; /* @508 zero */` becomes `__u32 flags;` (keep the static asserts at the same offsets);
   - add `DRM_G5P_CAP_RENDER_SKIP_EMPTY_TILES (1ULL << 32)` and `DRM_G5P_RENDER_PASS_SKIP_EMPTY_TILES (1U << 0)`
     under `#ifndef` guards, like `RENDER_PIXEL_OUTPUT_WIDTH`.
2. `g5p_record.c` + `g5p_job.h`: add `bool g5p_job_skips_empty_tiles(const struct g5p_render_job *j)`, defined as
   ```c
   (j->evidence & G5P_EV_LOAD) && j->samples == 1 &&
   (!j->depth.present || ((!j->depth.zstore || j->depth.zload) && (!j->depth.sstore || j->depth.sload)))
   ```
   - The ICD already tracks the inputs:
     - `G5P_EV_LOAD` is set by `g5p_job_begin` for LOAD (and for DONT_CARE in a partial area);
     - `g5p_job_clear` drops it when an in-pass full clear replaces the background;
     - MRT passes can't LOAD (`mrt_admit`), so they never skip;
     - a depth/stencil aspect that is stored without being loaded was cleared or is undefined, so its empty tiles
       must be written;
     - `g5p_job_clear_ds` clears `zload`/`sload`, so the rule sees it.
   - This is pvr's rule (`pvr_arch_cmd_buffer.c:1570-1580, 1725-1730, 1948-1957, 10086-10112`) on our recorder.
3. `g5p_drm_render.c` `typed_submit`, V3 branch: if `drm->info.capabilities & DRM_G5P_CAP_RENDER_SKIP_EMPTY_TILES`
   and `g5p_job_skips_empty_tiles(j)`, set `pass3.flags |= DRM_G5P_RENDER_PASS_SKIP_EMPTY_TILES`. Never touch the trace
   JSON, so the scene records stay byte-identical.
4. `g5p_gfx_test.c`: a unit scene for `g5p_job_skips_empty_tiles()` over hand-built jobs:
   - true: LOAD, colour only; LOAD with depth that loads and stores; DONT_CARE in a partial area;
   - false: CLEAR; LOAD then a full `vkCmdClearAttachments`; MRT; depth CLEAR+STORE; stencil CLEAR+STORE.

   The existing recorded scenes must stay byte-identical. The fake node (`build/gpu/hyprland-gpu/offline/host/a9-fake-node-hypr.c`, caps at line 717) does not advertise
   bit 32, so offline runs never set the flag.

### 7.4 Merge with the clock lane: clean

- `a9/perf60-clock@9d732490c2` touches `drm-render.inc` (three `g5p_gpc_ok()` call sites) and `drm-latency123.inc`
  (the GPUPERF line). Those hunks are disjoint from perf60's, and `git merge-tree` reports no conflict.
- The merge commit is `a9/perf60-next@50acfa8020` (= `perf60-empty` + `perf60-clock`; 18 files, +307/−22 against
  release7). Nothing needed resolving.
- Combined build: `PERF60_BRANCH=a9/perf60-next PERF60_NAME=perf60n scripts/gpu/perf60-build.sh build|package`
  (record in §7.6).

### 7.5 Device proof of the contract (after round 1, on `perf60n` or `perf60-empty`)

- **Fixture v3** (§8.4; it supersedes v2): `build/gpu/perf60/perf60-fixture3.tar.gz`. It adds `fill_clear_small`: a CLEAR pass whose only geometry is the 64×64 quad, so
  every other tile must still get the clear colour.
- Offline over the fake node: 6/6 rungs, 0 refusals.
- **With today's ICD** (no flag) and `render_user_skip_empty_tiles=Y`:
  - the result must equal `base`;
  - P60 `w3c0=0023000f` on every job;
  - every rung PASS.
  - This proves the kernel default and the gate are inert.
- **With `perf60_empty_tiles=1`:**
  - `fill_clear` and `fill_clear_small` FAIL (empty tiles stale; `w3c0=0021000f`);
  - `fill_load_small` PASS and fast.
  - This shows why CLEAR passes need bit 17.
- **With an ICD built from §7.3** and `render_user_skip_empty_tiles=Y`:
  - all six rungs PASS;
  - P60 shows `w3c0=0021000f` on the LOAD rungs (`solid`, `blit`, `load_small`, `load_scissor`) and `0023000f` on the
    CLEAR rungs (`clear`, `clear_small`);
  - `fill_load_small`'s `td` drops like the override arm's.

  That is the proof: CLEAR passes still write every tile, and LOAD passes skip empty ones. Only then does the gate's
  default flip to Y.

## 8. Rounds 0–2 on hardware, and the per-tile cost

### 8.1 Results [V] (orchestrator's run on perf60 b2d7c04e83, `build/gpu/perf60/fill-ab/summary.txt`)

Fixture 3D time `td` (ms, slots 12/11, 1536×2048):

| arm | clear | solid | blit | load_small | load_scissor |
|---|---|---|---|---|---|
| base | 11.5 | 17.6 | 35.7 | 30.2 | 29.4 |
| pte_variant 1/2/3 | ≈ base | ≈ | ≈ | ≈ | ≈ |
| perf60_empty_tiles=1 | 4.2 (FAIL as predicted, `w3c0=0021000f`) | 17.1 | 35.4 | **4.7** | **4.5** |
| poll 200/100 µs | 10.6 | 16.6 | 35.2 | 29.2 | 29.2 |

- **Memory attributes are ruled out.** No variant changes any rung, so §0.3's leading suspect is refuted.
- **Tile skipping works,** and the tiler bins by the scissor: ×6.4 on small damage. §7 is the proper form.
- **Polling barely matters.**
  - TA event 7.9 → 7.2 ms; `td_cons` 2.0 → 0.8 ms; tail 1.0 → 0.07 ms.
  - So the TA's ~7 ms is firmware-internal, and §0.4's quantization hypothesis is refuted for the TA.
  - Faster polling still saves ~2 ms of host edges per job.
- **Round 2:** Hyprland went from 1.80 to 2.06 FPS. es2gears at 744×970 damages ~90 % of the panel, so the frames
  are full-damage, and the per-tile cost itself is the next lever.

### 8.2 What the per-tile numbers say [V numbers, I reading]

- Fixed per-job 3D cost ≈ 4.2 ms (empty1 clear: no tile is processed).
- **Store:** clear − fixed ≈ 7.3 ms for 12.6 MB ⇒ **~1.7 GB/s PBE store** into a linear 6144-B-pitch target.
- **Background load:** solid − clear ≈ 6 ms for 12.6 MB ⇒ ~2 GB/s. This is Apple's LOAD program (captured, `load.json`)
  reading the same linear image.
- **Texture fetch:** blit − solid ≈ 18 ms for 12.6 MB ⇒ **~0.7 GB/s** through our compiled fragment shader's USC `smp`
  (texelFetch, `tex_f32`).
- **Reading:** the same bytes, the same linear layout and the same image are read ~3× slower by our sample path than
  by Apple's load program. So layout alone does not explain the blit; the sample path does (instruction form, return
  width, waits, occupancy).
  - Our Hyprland texture program (`g5p-shaderc` on `regress/gfx/hypr-tex.frag.spv`): 64 B USC, 8 temps, one
    `1a f5 04 01 08 84` sample, then four per-channel ops.
  - Apple's LOAD USC is 116 B and was never compared instruction for instruction against a sample of ours. That is the
    first offline task for the ICD owner (below).
- The cluster/USC enables are Apple's (§2) [V], so (d) has nothing new to flip.
- Occupancy (temps → instances in flight) is the open part of (d). `solid_alu16` and `blit_lin_2tex` measure it
  indirectly.

### 8.3 What can be A/B'd now, and by whom

The kernel cannot change texture state, sample instructions or PBE words: they are userspace words (state BO, USC code,
EOT program) that the kernel treats as opaque. So runtime knobs for (a)–(c) belong in the ICD, under
`src/imagination/vulkan/g5p`, which this lane must not edit (§7.3). Two things are measurable without an ICD change:

- **(a) source layout and filter:** the fixture's blit matrix (§8.4). The G5P ICD twiddles an OPTIMAL 2D image with
  more than one level (`g5p_mem.c` `wants_twiddled`), so a 2-level `glTexStorage2D` sampled at level 0 is a twiddled
  source. That is [I] from the code; the fake node does not log layouts.
- **(c) store pitch sensitivity:** the same 3072 tiles at a different row pitch, via `FILL_W`/`FILL_H` on
  `perf60-ab-device.sh`. If the store cost follows the pitch, the linear PBE's row bursts are the limit, and a
  twiddled/tiled intermediate target (Apple's `pass` vs `pass-linear` captures hold both PBE forms) is the fix.
  - 768×4096 (3072-B pitch) and 3072×1024 (12288-B pitch), against 1536×2048.

Knobs and offline comparisons for the ICD owner (Mesa → Codex per routing), proposed as `PVR_G5P_*` env knobs read at
pipeline/image creation:

1. `PVR_G5P_TWIDDLE_SAMPLED=1`: twiddle single-level OPTIMAL sampled 2D images (not exported, not render targets).
   Pairs with `blit_tw_*` vs `blit_lin_*`.
2. `PVR_G5P_RT_TWIDDLED=1`: build Apple's twiddled PBE target (the `pass` capture's PBE words vs `pass-linear`) for
   non-exported colour attachments. Hyprland's offscreen framebuffers would then store as 4 KB contiguous tiles; only
   the final scanout copy writes linear.
3. **Sample form:** compile the fixture's blit (`texelFetch` and `texture(t, uv)`) and compare with Apple's
   `metal-tt -arch applegpu_g5p` output for the equivalent Metal shader:
   - the result width (f16 halves vs f32);
   - any fence/wait after `smp`;
   - temps (`DOUTU` temp count → occupancy).

   A knob for whichever differs.
4. **Texture state words for a linear 2D source vs Apple's:** never captured for textures (`labwc110-texture-blend.md`
   row "texnarrow", `gles3-tex.md`). A one-shot iOS capture of a full-screen `texture2d<half>` blit from a linear
   IOSurface-backed texture settles q1/q2 (stride, cache bits).

### 8.4 Fixture v3 and the next package

- `fill-ladder` `4b10fdfe4154…`, overlay
  `build/gpu/perf60/perf60-fixture3.tar.gz` `56635e261df9…`
  (`perf60-ab-device.sh` unchanged, `62cfc767…`).
- 14 rungs, offline over the fake node: 14/14, 0 refusals.

| rung | source | sample | splits |
|---|---|---|---|
| `fill_blit` | linear, 1 level | texelFetch | baseline |
| `blit_tw_fetch` | twiddled (2 levels) | texelFetch | layout |
| `blit_lin_nearest` / `blit_lin_bilinear` | linear | `texture()`, NEAREST / LINEAR at texel centres | filter, coordinate path |
| `blit_tw_nearest` / `blit_tw_bilinear` | twiddled | as above | layout × filter |
| `blit_lin_2tex` | linear | two samples per pixel (same texture, two samplers) | per-sample cost: ≈2× blit's increment means sample-bound |
| `blit_lin_varying` | linear | `texture(t, uv)`, interpolated uv | Hyprland's shape |
| `solid_alu16` | – | 16 dependent FMAs | ALU / occupancy: ≈ solid means ALU is free |
| `fill_clear_small` | – | CLEAR + one 64×64 quad | the §7 contract proof |

- Bilinear rungs at texel centres should be exact. A FAIL with tiny differences is the TPU's sub-texel precision, not
  a fault; the time is still valid.

Next device run, on the combined kernel `perf60n` (§8.5) or on perf60:
*(Device/host command block omitted; it targets the private workspace.)*
- `skipgate` only exists on perf60n/perf60-empty; on perf60 the script skips that arm and says so.
- With today's ICD, `skipgate` must equal `base`, with `w3c0=0023000f` everywhere (§7.5).

### 8.5 Combined kernel `perf60n` (`a9/perf60-next@50acfa8020` = fill knobs + per-pass empty tiles + clock lane)

- Release `7.3.0-rc1-perf60n-g50acfa80206e`, config byte-identical to release7's. The build has no warnings; the
  merge compiles.
- Package checks passed: cmdline (entry renamed), initramfs and dtb are all release7's. The image has the markers
  `perf60_empty_tiles`, `perf60_poll_us`, `perf60_log`, `render_user_skip_empty_tiles`, `gpc_any_pstate` and
  `boot_gpu_perf`, plus release7's.
- Payload `build/boot/m1n1-linux-perf60n-50acfa8020.bin`:
  **`935a5d1b02d5…`**.
- Entry `perf60n-50acfa8020` (`build/gpu/perf60/perf60n/`):
  - `Image.gz` `a064b8cd…`
  - `dtb` `40ee1e67…` (= release7's)
  - `initramfs.gz` `de6b2f70…` (= release7's)
  - `cmdline` `8d6ce702…`
  - `entry.sha256`, `entries.env`
  - patches `perf60n.patch` (three commits on release7).
- Every new knob defaults off, so with no parameter set the kernel behaves as perf60's base arm. The clock lane's
  `boot_gpu_perf` is latched at map: that is a boot parameter in the clock lane's plan, not part of this lane.
- Hop: §4 round 1's sequence with `P60=build/boot/m1n1-linux-perf60n-50acfa8020.bin`, the hash above and
  `ENTRY=perf60n-50acfa8020`.
- Build: `PERF60_BRANCH=a9/perf60-next PERF60_NAME=perf60n scripts/gpu/perf60-build.sh build`, then `package` with
  `PERF60_MARKERS="render_user_skip_empty_tiles gpc_any_pstate boot_gpu_perf"`, then `restore`. The release7 worktree
  is back on `a9/release7@802a3d4fc4`, clean.

### 8.6 Kernel branches (all unpushed; the orchestrator syncs them)

| branch | tip | content |
|---|---|---|
| `a9/perf60-fill` | `b2d7c04e83` | round 0–2 knobs (flown) |
| `a9/perf60-empty` | `06ef780212` | + per-pass SKIP_EMPTY_TILES contract, gate default N; release7 host gates PASS |
| `a9/perf60-next` | `50acfa8020` | `perf60-empty` merged with `a9/perf60-clock@9d732490c2`, no conflict |

## 9. ICD side (2026-11-03): §7.3 written, §8.3 compared (branch `g5p-perf60-empty`, private fork)

- **Commits** on `g5p-hypr-s1fix@002a9ff0e4e`:
  - `26613cbb172` SKIP_EMPTY_TILES;
  - `38a8a95a8ec` `PVR_G5P_TWIDDLE_SAMPLED=1`;
  - `72a142b028d` gfx-test include.
  - Built in s1fix's configured tree (`HYPR_LANE=perf60e scripts/gpu/hypr-gpu.sh`; check the branch out in
    `mesa-a9-hyprs1fix-src` first).
- **§7.3, as specified:**
  - `g5p_pass_v3.flags` replaces `pad` @508; cap bit 32 and pass bit 0 sit under `#ifndef`;
  - `g5p_job_skips_empty_tiles()` implements the rule; the V3 submit sets the flag when the kernel offers cap 32;
  - `PVR_G5P_SKIP_EMPTY_TILES=0` never sets it (A/B);
  - the trace JSON is untouched.
  - g5p-gfx-test `scene_skip_empty_tiles`: 11 hand-built jobs. True: LOAD, DONT_CARE partial, depth L+S, D+S L+S,
    depth L only. False: CLEAR, LOAD then full clear, MRT, 4×, depth CLEAR+STORE, stencil CLEAR+STORE.
- **Gates:**
  - regress against the s1fix build: 270/270 compiles identical, every scene byte-identical, gfx-test passes in all 4
    orders (+1 for the new scene);
  - blend-ladder offline 64 rungs and qsladder offline, 0 refusals.
  - The fake node lacks cap 32, so offline never sets the flag.
- **Rungs** (blend-ladder):
  - `empty_clear_small`: a CLEAR pass whose only draw is a 64×64 box; every other tile must hold the clear colour.
  - `empty_load_small`, `empty_load_small_premult`: a LOAD pass after a finished one, 64×64 box; every other tile must
    keep the earlier pattern.
  - They are only meaningful on `perf60-empty`/`perf60n` with `render_user_skip_empty_tiles=Y`.
- **§8.3 knob 1** `PVR_G5P_TWIDDLE_SAMPLED=1` (default off): twiddles single-level OPTIMAL 2D images used only for
  sampling and copies. GL textures from Mesa's state tracker carry the colour-attachment usage, so for Zink clients it
  stays inert. Fixture v3's `blit_tw_*` vs `blit_lin_*` is the layout measurement.
- **§8.3 item 3, Apple vs ours** (`tools/mesa-a9-hyprland-gpu/tex-probes.py`, `build/gpu/perf60/tex-probes`; ours in
  `build/gpu/perf60/tex-ours`):

  | shape | Apple (applegpu_g5p, BGRA8 target) | ours |
  |---|---|---|
  | `texture(uv)` → output (Hyprland's passthru, the scanout copy) | `08130003 0080` iterator + narrow (bytes omitted) + wait + emit, 20 B | **byte-identical** |
  | `texture(uv) * uniform` (Hyprland's surface shape) | narrow sample, then 4 f16 multiplies by the common, 68 B | **wide `1af5`** (f32 return, 4 dwords) + `mov.shared` + 4 f32 `fmul`+pack, 64 B, 8 temps |
  | `texelFetch` → output (fixture `fill_blit`) | integer coordinates, narrow fetch (bytes omitted) (variant `4a`, not decoded), 88 B | **wide `texture.lod` `1af5…c6`**, float coordinates, 4 pack `fmul`s, 166 B, 12 temps |

  Apple returns f16 (`narrow`) for a UNORM8 target even from `texture2d<float>`. Fixture v3 already A/Bs exactly this:
  `blit_lin_varying` (our narrow program, Apple's bytes) vs `fill_blit` (our wide texelFetch), same linear image. If
  varying ≈ 2 GB/s and fetch ≈ 0.7 GB/s, the wide return is the cost.
  - The ICD knob for Hyprland's surface shape (narrow sample + f16 `half_binary_shared` multiply, the blend
    epilogue's witnessed f32-common form) is the next step after that number.
  - It only covers unblended draws: a blended draw saturates the source, and no half saturate is witnessed.
- **Knob 2** (`PVR_G5P_RT_TWIDDLED`): **not buildable yet.**
  - Rendering into a twiddled image is refused today (textypes.md §9: PBE form captured, not built).
  - The LOAD background of a twiddled attachment has never been captured.
  - Needs both, and a store-pitch result (fixture v3 `pitch3k`/`pitch12k`) to justify it.
- **Knob 4:** needs the one-shot iOS capture §8.3 describes: a full-screen `texture2d<half>` blit from a linear
  IOSurface-backed texture.
- **Package** `build/gpu/hyprland-gpu/perf60e/package/hypr-s2-a9.tar.gz`
  `4945014369bd…`: ICD `4ec53ad4c9f3…`,
  `mesa=g5p-perf60-empty@72a142b028d`. It also carries `PVR_G5P_FOLD_CLEAR`, default off.

## 9. Round 3: a uniform throttle. Measuring the real clock (1), and our programs against Apple's (2)

### 9.1 Round 3 [V] (orchestrator, `build/gpu/perf60/fill-r3/`, perf60n defaults)

- `skipgate` = `base`: the gate is inert, and perf60n renders the desktop correctly.
- `td` (ms):

  | rung | td |
  |---|---|
  | clear | 11.2 |
  | solid | 17.7 |
  | fill_blit | 36.3 |
  | blit_lin_varying | 33.2 |
  | blit_tw_* | ~30 |
  | blit_lin_2tex | 33.3 |
  | **solid_alu16** | **62.3** |

  - `pitch3k` brings the linear blits to ~30 ms; `pitch12k` = base.
  - Filtering costs nothing, a second sample is nearly free, and twiddled saves ~6 ms.

### 9.2 Throughput arithmetic [I, from the numbers above]

- `solid_alu16` − `solid` ≈ 44.6 ms for 16 vec4 FMAs per pixel.
  - Apple's compiler makes that 64 scalar FMAs (§9.3).
  - Over 3.15 Mpx that is ≈ 201 M FMAs: ≈ 4.5 G FMA/s, ≈ **13 FMAs per cycle at 340 MHz**.
- That is about one 16-lane USC pipeline's worth. The A9 has 6 USC clusters in 2 cluster groups (`dsx-nx78` §0).
- A pure clear stores ~1.1–1.7 GB/s.
- Everything is slow by a similar factor, so the limit is global:
  - **either** the GPU does not run at 340 MHz during the job (the clock lane: policy state 2, Fender 0x10/0x11
    churn);
  - **or** only a fraction of the clusters (or pipes) do work (power islands, firmware-managed unit count:
    `ROGUE_FWIF_POW_NUM_UNITS_CHANGE` exists in the family, `dsx-r74-power-handshake.md`; our init records never set a
    unit count; Apple's value is [O]).
- `perf60_cycles` (§9.4) separates the two: cycles per wall-µs during the 3D phase.

### 9.3 (2) Our programs vs Apple's [V: both compilers' output]

`tools/mesa-a9-perf60/occupancy.{metal,py}` compiles the fixture's shapes with Apple's A9 compiler
(`metal-tt -arch applegpu_g5p`, BGRA8 target; output `build/gpu/perf60/occupancy/apple.txt`). `glsl/*.frag` compiles the
same shapes with ours (glslang → `g5p-shaderc --groups last-read`; `build/gpu/perf60/occupancy/ours/`).

| shape | Apple | ours | difference |
|---|---|---|---|
| varying-UV sample (`blit_lin_varying`) | (bytes omitted) (20 B) | **byte-identical** (20 B, `tex_capture`) | none |
| texel read (`fill_blit`) | 88 B: coordinate conversion, `18f5…` sample **into the output registers**, `emitpix` | 166 B: longer coordinate path, `1af5…` sample into temps (f32), four f32→f16 packs, 12 temps | ~3 ms of 36 (the measured `fill_blit` − `blit_lin_varying`) |
| solid colour | 70 B: four `8a` moves + `emitpix` | 100 B: mov/mov.imm + four `89` packs | small |
| 16 vec4 FMAs | 1034 B: 64 scalar `9e` FMAs, per channel | the fixture's (via Zink) compiles; glslang's integer loop form is refused (`integer ALU: operand has no register`) | – |

- Apple's `__GPU_METADATA` field `r.0.1` reads 8 for solid/FMA and 12 for read/sample. Ours: temps 8, 12, 8.
  Occupancy by temps is comparable [I].
- **Conclusion:** for `blit_lin_varying` we run Apple's exact fragment program and still take 33 ms. So the per-pixel
  program is not the cap. What remains of (2) is the per-instance allocation outside the USC code: the fragment PDS
  program and state words (DOUTU temps, `usc_sharedsize`, PDS temp/data sizes, the unified-store partition). These
  are ICD words; compare them with the `pass`/`load` captures' PDS words for the same shapes (ICD owner).
- The texel-read form (op `0x18` into outputs) is a small, separate ICD win.

### 9.4 (1) `perf60_cycles`: the clock a job really ran at — **RETIRED: it froze the SoC (§9.7). Never fly perf60c/perf60c2.**

- Kernel `a9/perf60-cyc@627de340e7` = `a9/perf60-next` + one commit. With `perf60_log=1` and `perf60_cycles=1` (0600,
  default off), each TYPED_V3 job prints three `RENDER-P60C` lines: before the TA publish, before the 3D publish, and
  at the 3D completion.
- Each line carries the Fender pstate word (R1+0x1000, always read) and, if `g5p_gpc_ok()` admits R0 then:
  - `ROGUE_CR_TIMER` (R0+0x160);
  - `PERF_TA_PHASE`, `PERF_3D_PHASE`, `PERF_TA_CYCLE`, `PERF_3D_CYCLE`, `PERF_TA_OR_3D_CYCLE` (R0+0x6008/6010/6020/6028/
    6038).
- These counters ran at exactly 340.00 MHz on the stalled-TA boots (`dsx-nx20` §3.4).
- **Unlike every other perf60 knob, this one reads registers.** ~~It is guarded like every R0 access in the driver~~ —
  **wrong**: the Fender read was unguarded and two of the three points come after a retirement (§9.7).
- `perf60-summary.py` prints, per rung, `3D_CYCLE` and `TA_OR_3D` MHz between the 3D publish and the 3D completion,
  the raw `3D_CYCLE` at completion (in case the hardware zeroes it at the kick), and the pstate words seen.

**How to read it:**

| result | meaning | next |
|---|---|---|
| ≈ 340 MHz during the 3D (or the pin-100 clock) | the clock is not the cap: we really use ~1/6 of the shader array | cluster/dust power: the unit count the firmware powers, Rogue `POW_NUM_UNITS`, the SPU/dust power status registers; and the PDS allocation words (§9.3) |
| ≪ 340 MHz, or `PERF_3D_CYCLE` flat while 3D is busy | clock-gated or parked during the job | the clock lane's policy state / `pol34` fix (pin-100 run) |
| `ok=0` at point 2 (R0 refused) | the GPC is parked by the time the 3D completes | read the Fender words only; the pin-100 run should then show `ok=1` |

### 9.5 ~~DEVICE-READY~~ RETIRED: perf60c (froze the SoC on hardware, §9.7)

- **Kernel** `a9/perf60-cyc@627de340e7` (on `a9/perf60-next`: fill knobs + empty-tile contract + clock lane +
  `perf60_cycles`). Release `7.3.0-rc1-perf60c-g627de340e7a3`; config, dtb, initramfs and cmdline are release7's
  (entry renamed). The build has no warnings, and the markers include `perf60_cycles` and the clock lane's knobs.
  - Payload `build/boot/m1n1-linux-perf60c-627de340e7.bin`:
    **`8ffc4378b6ea…`**.
  - Entry `perf60c-627de340e7` (`build/gpu/perf60/perf60c/`, `entry.sha256`, `entries.env`); `Image.gz` `b57e94ac…`.
  - All knobs default off, so a boot without parameters behaves as perf60n.
- **Overlay v4** `build/gpu/perf60/perf60-fixture4.tar.gz`
  `863449c3739b…`: `fill-ladder` as v3 (`4b10fdfe…`), and
  `perf60-ab-device.sh` `09d21fee…` (now also saves and restores `perf60_cycles` and `render_user_skip_empty_tiles`).
- **Run** (hop as in §4 round 1 with this payload and `ENTRY=perf60c-627de340e7`, then the session):
  *(Device/host command block omitted; it targets the private workspace.)*
- Read with §9.4's table. One arm suffices: `solid_alu16` and `fill_clear` carry the answer. The other rungs come for
  free.

### 9.1 Small damage: which pass still touches every tile (2026-11-03)

- **Device (perf60e, gate Y):** foot cursor blink, 36.3 ms median 3D (N: 41.7). The skip saves only ~5 ms.
- **Hyprland 0.56.2 per frame** (source):
  - `begin()` binds a work buffer that `end()` of the previous frame **invalidated**; `clearAfterInvalidation()`
    clears it **full** (unscissored `glClear`);
  - `renderBackground()` adds a clear element (Omarchy: `disable_hyprland_logo`) drawn as one scissored
    `glClearBufferfv` per damage rectangle;
  - the damage-scissored scene;
  - `end()`: the scanout copy, one scissored draw per damage rectangle (`renderTexturePrimitive`).
  - The full clear has no setting: for 8-bit output `end()` always invalidates (`debug:invalidate_fp16` only covers
    FP16).
- **Our passes** (offline, foot blinking, `offline/small-a`, `small-b`, `small-log`): the full clear is the pass's CLEAR
  load. The damage clears that follow arrive before any draw as partial `vkCmdClearAttachments`, so `clear_split()` ran
  the still-empty pass as a **CLEAR_ONLY job**: a CLEAR pass, so by §7.3 every tile is processed and stored. Then come
  the CPU rectangle clears, then the LOAD scene pass and the LOAD copy.
- **With `PVR_G5P_FOLD_CLEAR=1`** (`002a9ff0e4e`: the empty job's clear goes to the CPU, full view, then the
  rectangles), `PVR_G5P_PASS_LOG=1` offline shows the steady state:
  ```
  812 G5P pass 1280x720 load=1 clear_only=0 skip_flag=0 rule=1 draws=12 tiles=34/920   (scene)
  812 G5P pass 1280x720 load=1 clear_only=0 skip_flag=0 rule=1 draws=1  tiles=34/920   (scanout copy)
  ```
  No CLEAR_ONLY pass is left. Both passes are LOAD with the rule met and touch 34 of 920 tiles (`skip_flag` is 0 only
  because the fake node has no cap 32).
- **Semantics:** the CPU clear writes the clear colour everywhere, as Vulkan requires; nothing is skipped that must be
  written.
- **The proper end state** is Hyprland clearing only what it uses: `CGLFramebuffer::clearAfterInvalidation()`
  scissored to `m_renderData.damage` (the copy reads only the final damage, and the damage clears and draws cover it).
  That needs a rebuilt Hyprland 0.56.2 for the device; not done. The fold then degrades to a no-op.
- **Package** `build/gpu/hyprland-gpu/perf60e/package/hypr-s2-a9.tar.gz`
  `62cf5628bef2…`: ICD `ce58a885c733…`,
  `mesa=g5p-perf60-empty@b80ccd064a9` (+ `PVR_G5P_PASS_LOG`). Regress: 270/270 identical, scenes identical.

### 9.6 ~~DEVICE-READY~~ RETIRED: perf60c2 (same reads as perf60c, §9.7)

- **Kernel** `a9/perf60-cyc2@2eca5f8fbd` = `a9/perf60-cyc@627de340e7` merged with the clock lane's fix
  `a9/perf60-clock@4a0eafe14b` (ctrl+0x1038/0x1040 override writes). No conflict (2 files against perf60-cyc).
  - Release `7.3.0-rc1-perf60c2-g2eca5f8fbd45`, config byte-identical to release7's. The build has no warnings; the
    markers include `perf60_cycles`, `render_user_skip_empty_tiles`, `gpc_any_pstate` and `boot_gpu_perf`.
  - Payload `build/boot/m1n1-linux-perf60c2-2eca5f8fbd.bin`:
    **`3c4f1e4b01ff…`**.
  - Entry `perf60c2-2eca5f8fbd` (`Image.gz` `9779ee8e…`); dtb, initramfs and cmdline are release7's (entry renamed).
  - `build/gpu/perf60/perf60c2/` is in release7's layout (`entry`, `release`, `payload.sha256`, `entry.sha256`,
    `cmdline`, `cmdline-sd`, `labwc/`, `entries.env`), so the clock lane's runner drives it unchanged.
  - The self-checks passed: entry hashes, payload hash, labwc hash.
- **Build note:** the build's own last step reported rc=2. That was not the kernel. I edited `perf60-build.sh` while
  it ran, and bash read on at a shifted offset and ran `restore`'s `make clean` on the host, where it fails harmlessly.
  - The image, COMMIT (`2eca5f8fbd`), RELEASE and the empty DIRTY were all written before that.
  - The workspace repo is untouched.
  - `package` and `restore` then ran normally; the release7 worktree is back on `a9/release7@802a3d4fc4`, clean.
- **Runner change:** `scripts/gpu/perf60-clock-device.sh` now takes its package directory from `PERF60_CLOCK_PKG`
  (default `build/gpu/perf60-clock`, so the clock lane's flow is unchanged).

**The arm the orchestrator asked for: policy held at pin 100, cycles measured.**
*(Device/host command block omitted; it targets the private workspace.)*
- Also look for the `GPUPERF boot pin=100 … ovr=400/100` line at map, and `pol34=1 ps=00000001` in the per-job
  GPUPERF lines (clock lane §1).
- Read the `[rung] P60C … 3D_CYCLE … MHz` lines with §9.4's table, for `fill_clear` and `solid_alu16` above all:
  - ≈ 340 MHz with the policy held, and the rungs as slow as round 3: the clock is not the cap. Next is cluster power
    or the PDS allocation words (choose after the results; nothing started).
  - Far below 340 MHz on defaults but ≈ 340 MHz here, with the rungs much faster: the clock was the cap.

### 9.2 Device pass log (`build/gpu/perf60/pass-plA.txt`, `pass-plB.txt`): the scissor is full because the damage is

- **Device:** every LOAD pass is flagged (`skip_flag=1`), but even the 1-draw scanout copy has `tiles=3072/3072`. The
  fold works (B: no CLEAR_ONLY).
- **`tiles=` is computed in our draw path:** each draw's `dyn->vp.scissors[0]` clipped to the render area (the same
  rectangle the ISP scissor gets). So the scissor Zink handed us was the whole target.
- **(a)** The scissor reaches the tiler: the fixture's scissored rung ran at 4.5 ms, and offline Hyprland's passes
  logged `tiles=34/920`.
- **(c)** Transform 3 only transforms the damage rectangles (`scissor(&RECT, transformDamage)`). No full-target
  render + blit.
- **(d)** Hyprland 0.56 scissors per damage rectangle: the scanout copy (`renderTexturePrimitive`: `forEachRect` →
  scissor → draw), the background clear element, and the surfaces (damage-clipped).
- **So Hyprland's frame damage on the device is the whole monitor.** Buffer age is ruled out: aquamarine's DRM
  swapchain has length 3, inside `DAMAGE_RING_PREVIOUS_LEN + 1 = 4`, and `damage_tracking` is the default 2. What is
  left (Hyprland source):
  1. **failed output commits:** `Renderer.cpp:2480` rolls back the swapchain and calls `damageEntire()` when
     `m_state.commit()` fails (logged only at TRACE). A commit refused while a flip is pending (GPU-bound, about 4
     frames/s) would make every next frame full;
  2. **`m_forceFullFrames`** (3 after mode changes);
  3. **a client committing full-surface damage on a full-screen surface every frame** (a quickshell layer: an overlay,
     the wallpaper, an animated element).
- **Device test** (owner session, foot blinking, 10 s):
  `hyprctl eval 'hl.config({ debug = { disable_logs = false, log_damage = true } })'`
  - Then the session log: `grep -E 'Damage: (Surface|Window|Monitor|Box)' <hypr log> | sed -E 's/[0-9]+, [0-9]+ wh/xy wh/' | sort | uniq -c | sort -rn | head`.
    A full-size `Surface` extent each frame names the client (cross-check with `hyprctl layers`).
  - `grep -iE 'commit failed|cannot commit|EBUSY|atomic' <hypr log> | head` for (1).
  - Optional: `debug:damage_blink = true` and a screenshot.

### 9.7 Incident: `perf60_cycles` froze the SoC (perf60c, 2026-11-02), and the rule it broke

**What happened [V netconsole, `build/omarchy/logs/netconsole.log`, tail 23:37:46]:**
- The hop to perf60c passed and Hyprland came up. `perf60-ab-device.sh cyc:perf60_cycles=1` started at uptime ~200 s.
- The log stops dead at 231.548 s with no fault line. The last line is `G2 event index=165 type=1 word1=00000002`: the 3D
  completion of a **Hyprland** job (seq 3245, slots 8/7), not the fixture.
- DFU was needed.

**What the code did at that moment [V `a9/perf60-cyc@627de340e7`, `drm-perf60.inc` `g5p_p60_cyc()` and its three
hooks in `drm-render-v3.inc`]:** with `perf60_log=1` and `perf60_cycles=1`, every TYPED_V3 job (every client's, not
only the fixture's) called `g5p_p60_cyc()` at three points.

| point | where | what has already happened |
|---|---|---|
| 0 | before the TA publish | the previous job retired; nothing is published yet |
| 1 | before the 3D publish | the TA retired (its completion decided); the 3D is not published |
| 2 | right after `g5p_rv3_wait()` returned COMPLETE for the 3D | **the 3D retired**: its G2 type-1 `word1=2` event was decoded and the completion sample taken |

At each point, in this order:
1. `readl(R1 + 0x1000)` (the Fender pstate word), **unconditionally, outside any guard**;
2. only if `g5p_gpc_ok()` accepted that value: `readq(R0 + 0x160)`, then five `readl(R0 + 0x6008/0x6010/0x6020/0x6028/
   0x6038)`.

- So point 2 performed an unguarded R1 read, and possibly R0 reads, immediately after the 3D retired. That is exactly
  when the firmware may park or transition the GPC.
- Points 0 and 1 are also after a retirement, with nothing in flight to prove the GPC active.
- The `g5p_gpc_ok()` test cannot license the R0 reads either: it is a time-of-check value from the same unsafe R1 read,
  and the GPC can park between that read and the R0 reads.
- Which access hung (the R1 read or an R0 read) is not knowable from the log. Both are the same class.
- §9.4's line "guarded like every R0 access in the driver" was **wrong**, and the review of this knob should have
  caught it against `STATUS.md`'s first hard rule.

**The rule (hard, for every perf60 knob and anything built on it).**

> **No host R1 or R0 MMIO after a retirement (TA or 3D completion decided, or between jobs), unless a license proves
> the GPC is active and settled at that instant. Never read the Fender word (`R1+0x1000`) unguarded.** A post-retirement
> R1/R0 access can freeze the whole SoC (DFU). This is `STATUS.md` "Rules learned the hard way" #1 (*"Never access GPU
> registers after a job retires"*); the latency/wake line kept every post-retire path RAM-only for this reason
> (`latency114` S8/S9, `latency115`, `latency117`). Measurement knobs are not exempt.

- All other perf60 knobs (`perf60_empty_tiles`, `perf60_poll_us`, `perf60_log`, `render_user_skip_empty_tiles`) are RAM
  only [V code]. So perf60, perf60n and perf60-empty stay valid.
- **perf60c (`a9/perf60-cyc`) and perf60c2 (`a9/perf60-cyc2`) are retired.** Do not fly them, and do not merge
  `627de340e7` anywhere. The branches are kept only as the record of the defect.

**Rework (design only; not built, not to be flown until the orchestrator says), in order of preference:**

1. **RAM only: firmware-written stamps, no host MMIO at all.**
   - **Exact GPU-side phase time:** the job's microsequence already has the firmware store two timestamps per phase
     into the work record: `ts0 {0x80000018, …}` / `ts1 {0x18, …}` to W+0x558/0x55c (TA) and W+0x8b4/0x8b8 (3D)
     (`render-user-layout.h:475-493`; `80b-marker2-marker3-gap.md`; `ds-ghidra-1-render-path.md` tags 0/1). They are
     taken from the firmware's timer loop (`0x80004f14..0x80004f44`), a fixed rate (~24 MHz per `73e-device-result.md`).
     - Reading W+0x8b4/0x8b8 from RAM after the 3D completion gives the 3D's GPU-side duration without host polling
       noise, which already tightens §8's numbers.
     - Cost: one RAM read per job, in the existing completion sample.
   - **Effective clock:** cycles still need a cycle counter. Two RAM-only leads, both needing firmware RE first:
     - (a) whether the firmware's own completion path stores `PERF_*_CYCLE` (or a busy-cycle count) into RAM. Rogue
       firmware keeps per-kick timing and HWPerf data; Apple's equivalent is unidentified;
     - (b) the governor's utilisation words `policy+0x8f0..0x934` (`fw_time_*`, "sampler window advances") and
       `meta+0x784/0x788` (abstime), firmware-written (iOS power capture `power-words.md`). On iOS the governor turns
       these into utilisation, so it may read the busy-cycle counters itself.

     Decode which counters feed them (shared Ghidra on the firmware listings), then read them from RAM around a job.
2. **Host MMIO only inside a proven-active window**, if 1 fails and the owner approves the residual risk:
   - reads only while a 3D phase is in flight: published, ring consumed, no completion event decoded, RAM idle words
     showing the 3D engine busy (latency123's `pstate_probe=2` "fresh busy rise" condition);
   - only for the fixture's own context (a knob naming its slot pair), never for the session's jobs;
   - Fender read first and R0 only if it reads exactly `0x01` (`gpc_any_pstate=0` semantics);
   - two samples inside the same busy window, never at or after the completion decision.
   - **Residual risk, stated:** the 3D can finish between the RAM busy sample and the MMIO read. Only long fixture
     passes (`solid_alu16`, ~60 ms) make that unlikely, never impossible. So this variant needs DFU readiness, and it is
     not recommended while option 1 is open.
3. **No cycles at all:** the clock-vs-clusters question can also be answered RAM-only by pstate:
   - run the fixture under the clock lane's working pins (340 vs 474 vs 723 MHz) once a dispatchable pin exists;
   - ALU-bound time scaling with the requested clock means the clock was honoured, so the ~1/6 throughput is cluster
     or unit power;
   - no scaling means the requested clock never reaches the shader array.

## 9.8 RAM-only rework: the firmware's own phase times (`perf60_stamps`)

### 9.8.1 What the firmware writes, and in which units (offline RE) [V decode, I where marked]

- **Per-phase elapsed time [V].** Every job's microsequence brackets each phase with `ts0 {0x80000018, result, ts, ts,
  seq}` and `ts1 {0x18, result, ts, ts+4, seq}`. Result is W+0x550 (TA) / W+0x8ac (3D); stamps are W+0x558/0x55c and
  W+0x8b4/0x8b8 (`render-user-layout.h` `g5p_ru_job()`). W is rebuilt from the job image every job.
  - `ts0` (`0x80004ef0`) reads `ROGUE_CR_TIMER` (`[GbP+36]+0x160/0x164`, hi/lo/hi until stable), so the *firmware*
    reads the timer, not the host.
  - It converts through the **correlation block `[GbP+100]`**: stamp = blk[+0] + ((CR − blk[+8]) × blk[+16]) >> 19
    (`0x80004f4c..0x80004fe0`, 64-bit multiply `0x8000a8c4`, `LSR #0x13`).
  - `ts1` (`0x8000628c..0x800062d0`) adds (now − start) into the 64-bit result word. So **W+0x8ac = the 3D phase's
    elapsed CR_TIMER ticks × K >> 19**, written by the firmware, readable from RAM after completion.
- **The timer's rate [P, confirmed 2026-11-03]: CR_TIMER ticks once per 256 core clocks.**
  - `r0-160-counter-re.md` §0.2 measured `R0+0x160` on an idle Linux boot at 77 ticks in 57 µs ≈ 1.35 MHz, which is
    340 MHz / 256.
  - r3clk (`build/gpu/perf60/r3clk/alu-723.txt`, `alu-948.txt`) timed CR_TIMER against the host clock under an
    ALU-bound job:
    - pstate 4 (723 MHz): 2823 kHz, × 256 = 722.7 MHz (cycle counters 722993 kHz);
    - overclock pstate 5 (948 MHz): 3703 kHz, × 256 = 948.0 MHz (948012 kHz).
  - So ΔCR × 256 = core cycles while the phase ran, the effective-clock measurement, from firmware-written RAM.
  - A brief interim correction ("24 MHz / 11 wall time") rested on the pin-200 probes' 0x88e ticks per
    "gap_us=1000". That 1000 µs was the `usleep_range(1000, 1100)` target, not a measured interval, so it is
    withdrawn.
- **Will the units be usable on our boots? [O, the first thing the log answers].**
  - On Linux the converted ring-4 trace stamps were not monotone (`80-stage6-stage7-start23-timing.md` §2.3: 48 % step
    backwards, |Δ| ~1e13).
  - So K = blk[+16] may be zero or garbage, and the block may be re-based mid-phase.
  - The knob logs the block's 8 words with every job. K ≠ 0 and constant, and `td_el` ∝ the host-observed 3D window
    across rungs, means usable.
  - K = 0 means the elapsed word is 0. Then the units need the correlation block that Apple's kext presumably fills.
    That is a host write into firmware data, a separate owner decision, not done here.
- **(2) Does the firmware store cycle counts or busy time anywhere else in RAM?**
  - **Completion path [V]:** no PERF_* cycle store. The only timing it writes is the `ts0`/`ts1` pair above.
  - **Governor [V, `r0-160-counter-re.md` §0.4]:** its utilisation accumulators `policy+0x908/+0x90c`, `+0x910/+0x914`
    and `+0x918/+0x91c` are fed from the same `R0+0x160`, scaled and `>> 0x13`. They are updated only by the sampler,
    which is off on our boots (`policy+4 = 0`).
  - So expect them static. The knob logs them (and `meta+0x784/0x788`) to confirm.
  - With the sampler off, the ts pair is the only firmware-written time source.

### 9.8.2 Kernel `a9/perf60-stamps@e017fa50be` = `a9/perf60-next` + one commit (no `627de340e7`)

- `perf60_stamps` (0600, default off) prints, with `perf60_log=1`, one `RENDER-P60S` line per TYPED_V3 job after it
  ended:
  - `ta_el`, `td_el` (64-bit W+0x550 / W+0x8ac);
  - the raw stamps;
  - `corr=<blk META addr>/<readable>` and the block's 8 words;
  - `gov=` policy+0x908..0x91c;
  - `abst=` meta+0x788:0x784.
- **§9.7 review:**
  - Every access is a CPU load of host memory: the W pages (`g5p_ru_page()`), the firmware image/root/shared pages
    (`g5p_compute_ram_word()`, the existing RAM helper; addresses outside those pages are reported unreadable, not
    read), and the policy/meta blocks (`g5p_l123_word()`).
  - They come after the existing coherent RAM read `g5p_rv3_fw_touch()` (Normal-NC loads) and a `dma_rmb()`.
  - A diff scan of the whole branch against release7 finds no new `readl`/`readq`/`writel`/`g->rgx`/`window[`. The
    only three hits are the clock lane's `== 1` → `g5p_gpc_ok()` edits of existing guards.
- `perf60_cycles` does not exist on this branch.
- W=1: no warnings in the driver object. checkpatch: 0 errors.
- `perf60-summary.py` prints per rung:
  - `td_el / host-µs` (raw, assumption-free);
  - K;
  - the effective 3D clock 256 × ΔCR / (td_ev − td_cons), with ΔCR = (td_el << 19) / K (CR_TIMER = core / 256,
    confirmed on r3clk, §9.8.1);
  - whether the governor words moved.

  Self-test: K = 2^19, 82,329 ticks over 62 ms gives 340 MHz.

### 9.8.3 Package and run (record in §9.8.5)

- Fly after the DFU sequence (bell test → memclk → damage log), on defaults:
  *(Device/host command block omitted; it targets the private workspace.)*
- With overlay v4, `perf60-ab-device.sh` does not list `perf60_stamps` in its save/restore set. It is read at each job and harmless
  if left on; set it back with `echo 0 | sudo -n tee $P/perf60_stamps`, or use overlay v5 (§9.8.5).
- **How to read it:**
  - `corr …/1` with K ≠ 0 and the same K on every job, and `td_el/host-µs` steady across rungs: the units hold.
    - effective clock ≈ 340 MHz: the clock is not the cap → cluster/unit power (or PDS allocation) next;
    - ≪ 340: the core clock is gated during the 3D → the clock lane's path.
  - `corr …/0` (block outside the host pages) or K = 0 / `td_el = 0`: no firmware time units on this boot. Fall back to
    §9.8.4.
  - `td_el` erratic with a constant K: the block is re-based mid-phase. Same fallback.

### 9.8.4 The "no cycles" plan (RAM only), for when the clock lane's bell route dispatches

- Fixture v4, three runs: `perf60-ab-device.sh base:`, once each on the clock lane's pins 100 / 200 / 400 (340 / 474 /
  723 MHz), through its own hop (`perf60-clock-device.sh hop <pin>`).
- Compare `solid_alu16` `td` (and `td − solid` ⇒ the ALU-only time), plus `fill_clear` as a fill-bound control. Every
  number is host-side RAM timing; no registers.

| ALU-only time vs pin | meaning |
|---|---|
| scales as 1/f (×0.72 at 474, ×0.47 at 723) | the requested clock reaches the shader array; the ~1/6 throughput (§9.2) is cluster/unit power or allocation |
| does not move | the requested pstate does not reach the shader clock (or the work is not clock-bound) |
| `fill_clear` scales but ALU does not (or the reverse) | the two paths have different limits; report both |

- With `perf60_stamps=1` in the same runs, `td_el` × 256 / td should track the pin's MHz if the units hold. That is a
  second, independent check of the /256 reading.

### 9.8.5 Build record: perf60s (DEVICE-READY, RAM only)

- Kernel `a9/perf60-stamps@e017fa50be` (on `a9/perf60-next@50acfa8020`: fill knobs, empty-tile contract, the clock
  lane's first commit; no `627de340e7`; the image contains no `perf60_cycles` string).
  - Release `7.3.0-rc1-perf60s-ge017fa50beeb`, config byte-identical to release7's. The build has no warnings, and
    the markers include `perf60_stamps`.
- Payload `build/boot/m1n1-linux-perf60s-e017fa50be.bin`:
  **`dc3e99d57792…`**.
- Entry `perf60s-e017fa50be` (`build/gpu/perf60/perf60s/`, release7's layout incl. `cmdline-sd`, `labwc/` and `entries.env`); `Image.gz`
  `17a017dc…`. dtb, initramfs and cmdline are release7's (entry renamed). The
  self-checks passed.
- Hop: the usual warm hop on defaults (§4 round 1's sequence with this payload and `ENTRY=perf60s-e017fa50be`, or
  `PERF60_CLOCK_PKG=build/gpu/perf60/perf60s` with the clock lane's runner for its pins). All knobs default off.
- **Overlay v5** `build/gpu/perf60/perf60-fixture5.tar.gz`
  `4e653aebd315…`: `fill-ladder` as v3/v4,
  `perf60-ab-device.sh` `d3f18e1f…` (saves and
  restores `perf60_stamps`; `perf60_cycles` dropped from the list).
- Run: `perf60-ab-device.sh stamps:perf60_stamps=1` (§9.8.3). Read it with §9.8.3's rules.
- The release7 worktree is back on `a9/release7@802a3d4fc4`, clean.

## 10. The remaining per-tile floor (ALU and clear), after bells + memclk (2026-11-03)

State from the orchestrator [V, the clock and memclk lanes]:
- never-park + host bells: ta 2 / td 4 ms per labwc job;
- SoC/memory state 12: blits 36 → 16 ms, solid 18 → 12, load_small 31 → 18;
- unchanged: **ALU 62 → 58** and **clear 12 → 12**. Both are not memory-bound.

### 10.1 Offline findings

1. **The init/power records hold no unit or cluster count that differs from iOS [V].**
   - Every field in the iOS capture's `power-words.md` where Linux differs from iOS (policy/meta/control; 104 fields)
     falls into three groups:
     - the known power/governor words (pstate table, gains, limits, governor time words);
     - three host platform flags: `meta+0x6c4 = (acc+0x510 >> 8) & 1` enables the per-tick routine `0x100044f0`
       (`wake-latency-re.md`); `meta+0x700` (acc+0xbbb4) and `ctl+0x20` (platform+0x510 bit 0) have no known reader
       (`governor-gate-wait-re.md`: unused by the tick);
     - pointers.
   - Nothing reads like a unit count or a cluster mask. No `POW_NUM_UNITS`-style command or field has been seen on
     either side.
   - Rascal/Dust islanding is firmware-managed; with it off we are more powered, not less (`dsx-nx20` §2.3).
   - [O]: the init record beyond these blocks (the LDR-defaulted part), and the firmware's own unit bring-up, which no
     capture holds.
2. **Per-instance allocation is Apple's for these shapes [V code, `g5p_record.c`].**
   - Fragment DOUTU temps come from the compiler (`g->fs.temps`: 8 for solid/FMA, 12 for texel read; Apple's metadata
     `r.0.1` reads 8 / 12).
   - Background, clear and EOT DOUTU temps are the captured 8.
   - `PDS_SIZEINFO1/2` and `BGRND3_SIZEINFO` follow the captured layouts.
   - The 3D partition words W3c4 / W3c8 / W3cc / W108..130 are Apple's filler formula (`6ca7ae0`, table `5942678`).
   - So occupancy by allocation words is not visibly different [I]. Whether a *dependent* chain is latency-bound is
     measurable (10.2).
3. **The clear is not store-row bound [V, round-3 pitch arms].**
   - `fill_clear` is 11.2 ms at 3072-, 6144- and 12288-byte row pitch (`fill-r3/perf60-20261102T2207*/2208*`), and
     `solid_alu16` is pitch-flat too. Only the blits move (36 → 30 at 3 K pitch).
   - Our linear PBE equals Apple's linear form. It differs from Apple's twiddled PBE exactly in dwords 0/3/5
     (`mrt.md`). The twiddled RT PBE is captured but not built in the ICD.
   - Clear − empty ≈ 6.7 ms over 3072 tiles ≈ **2.2 µs ≈ 740 GPU cycles per tile** for a 4 KB tile with a ~5-instruction
     background program. That is about one tile at a time.
4. **ISP_CTL `PIPE_ENABLE` is 0: one tile in flight in the Rogue reading [V words; I meaning].**
   - In Rogue cr.xml, ISP_CTL[15:12] is `pipe_enable`, documented "Tiles-in-flight". Upstream pvr computes it in
     `pvr_arch_setup_tiles_in_flight()` from the USC partitions, the cluster count and `isp_max_tiles_in_flight`, and
     writes `2 × tiles_in_flight − 1` on XT-top cores (`pvr_arch_job_common.c:388-501`).
   - **Apple's 3D filler never sets those bits** (`6ca7ae0` Ghidra C in `build/gpu/render-fixture-r22/filler-oracle.c:
     319`: W3c0 = {0x10000 | 0x30000} | D6a8 | (n−1)<<21 | D6b4<<18 | D6b7<<20). Ours is 0 as well (`0x0021000f`).
   - Either the A9 firmware or another A-block word (W3c4 = n × 0x204, not yet mapped to its CR) carries the
     tiles-in-flight setting on Apple's side, or the field means something else on A9.
   - "Serial tiles" fits both the clear (740 cycles/tile) and the ALU (≈ 13 FMA/cycle, about one cluster's worth).
     **Cheapest test: set it and measure (10.2).**

### 10.2 New A/Bs (RAM only, §9.7-compliant)

- **`perf60_isp_pipes` (kernel, 0600, default 0, read at each submit):** ISP_CTL[15:12] = N on every pass.
  - It edits the job's own staged W before publication, the same class as `perf60_empty_tiles`. No register access.
  - Measurement only: a value the hardware cannot sustain may hang the 3D. That ends in the usual job timeout and
    `render_user_recover`, or a warm hop.
- **Fixture v6, three new rungs:** `solid_alu16i` (the same 16 vec4 FMAs as four independent chains), `solid_alu64` and
  `solid_alu64i` (slope).

| result | meaning |
|---|---|
| `solid_alu16i` ≈ `solid_alu16` | issue-bound: units, clock, or tiles in flight starve the array |
| `solid_alu16i` ≪ `solid_alu16` (→ ~¼ of the ALU part) | a dependent chain is latency-bound: too few instances in flight (occupancy) |
| `perf60_isp_pipes` 1/3/7 makes `fill_clear` and `solid_alu*` drop | tiles in flight was the global cap; find Apple's mechanism and make it the proper default |
| no change at any N | the field is not the cap on A9; next: map W3c4/W3c8 to their CRs and the firmware's tile dispatch |

- Our compiler refuses glslang's form of the chained probes (`integer ALU: operand has no register`; the fixture's Zink
  form compiles), so the interleaving of `solid_alu16i` in our USC code is [O] until the device numbers.
- Offline over the fake node: 17/17 rungs, 0 refusals.

### 9.3 new_render_scheduling and the full damage: the decisive live test (2026-11-03)

- **Source (0.56.2):**
  - `render:new_render_scheduling` (off by default; the pass-log runs set it live) is `CMonitorFrameScheduler`.
    GPU-bound, `onSyncFired` renders an uncommitted third frame (`renderMonitor(m, false)`). `onPresented` commits it
    later (`commitPendingAndDoExplicitSync`) and schedules a frame "for missed damage".
  - The damage computation itself is unchanged. But any failed commit on that path does
    `swapchain->rollback(); m_damage.damageEntire()` (`Renderer.cpp:2473`, logged only at TRACE).
  - **`debug:damage_blink` forces full frames by itself** (`damageBlinkCleanup > 0`, `Renderer.cpp:2146`): use it for
    the screenshot only, never for tiles or timing.
  - Other full-damage triggers: `damage_tracking` ≠ 2 (not set), `m_forceFullFrames` (mode changes), and a client with
    full-surface damage on a full-screen surface (`debug:log_damage` names it).
- **Test** (pass-log ICD `62cf5628`, perf60n, gate Y; owner session, foot blinking, no gears, no input; 10 s per arm
  after 5 s of settling):
  1. `hyprctl eval 'hl.config({ render = { new_render_scheduling = false }, debug = { disable_logs = false, log_damage = true } })'`
  2. Measure:
     - slots 8/7 jobs/s and 3D median;
     - `grep 'G5P pass' <run>/hypr.log` for that window, `sed 's/va=[0-9a-f]*//' | sort | uniq -c`;
     - `grep -E 'Damage: (Surface|Window|Monitor|Box)' /run/user/1000/hypr/*/hyprland.log`, same window, histogram;
     - `grep -iE 'cannot commit|commit failed|page-flip' /run/user/1000/hypr/*/hyprland.log`.
  3. The same with `new_render_scheduling = true`.
  4. Visual only: `debug = { damage_blink = true }`, a scanout screenshot per scheduling value, then set it back to
     false.
- **Reading:**
  - Small `Damage:` boxes, small `tiles=`, a low 3D median with scheduling off, but full tiles with it on: the full
    damage comes from new scheduling's commit path. Keep it off.
  - Small `Damage:` boxes but `tiles=3072` with scheduling off: our ICD loses the scissor between Zink and the
    recorder on the device (transform 3 / scale 2 path). Fixed in the ICD next.
  - Full-size `Damage:` boxes: the client or the trigger they name.

### 10.3 Resolved on hardware: the per-tile floor was park churn [V, `build/gpu/perf60/flight-b/`]

- On the never-park + host-bell kernel (perf60cm, pin 100, labwc only), with fixture wall time in parentheses:

  | rung | td before → after |
  |---|---|
  | `fill_clear` | 12 → **2** ms (4.8 ms) |
  | `fill_solid` | 18 → **2** ms (6.6 ms) |
  | `fill_blit` | 36 → **4** ms (8.0 ms) |
  | `solid_alu16` | 62 → **8** ms (11.9 ms) |

- So the "~1/6 USC throughput" (§9.2) and the ~1 GB/s clear (§10.1.3) were the firmware parking and re-waking the GPC
  around the work. They were not cluster count, occupancy, PBE form or tiles in flight. §10.1–10.2's investigation is
  **closed**, by the orchestrator's call.
- `perf60_isp_pipes` stays in the perf60cms package at its default 0 (Apple's value). **Do not fly it**; it answered a
  question that no longer exists. The 10.2 ALU rungs stay in fixture v6 as cheap regression timers.
- Still useful from perf60cms: `perf60_stamps` on the bell kernel gives the firmware's own GPU time per phase (§9.8).
- **Offline pre-check of the ICD branch** (`offline/small-t3`): nested Hyprland with the device's monitor shape,
  `scale = 2, transform = 3` (`build/gpu/perf60/nested-t3/hyprland.lua`), foot blinking, pass-log ICD + fold. Steady
  state: the scene and copy passes **`tiles=92/920`** (865× copy, 580× scene; a few 920/920 startup frames). The
  rotated, scaled damage scissors reach our recorder intact, so on the device a small `Damage:` log with
  `tiles=3072` would point at the DRM path (commits, scheduling), not at the ICD's transform handling.

### 10.4 Build record: perf60cms (DEVICE-READY, labwc-only runs)

- **Kernel** `a9/perf60-cms@294091ddb3`, built from three pieces (no `627de340e7`; the image has no `perf60_cycles` string):
  - `a9/perf60-clockmem@4b61debe9d` (never-park + host bells, SoC/memory state 12);
  - merged with `a9/perf60-stamps@e017fa50be` (fill knobs, per-pass empty tiles, `perf60_stamps`) at `44af12335b`, no
    conflict;
  - plus `perf60_isp_pipes` (default 0; do not fly, §10.3).
- Release `7.3.0-rc1-perf60cms-g294091ddb3f7`, config byte-identical to release7's.
  - The build links clean, with no new warnings.
  - The markers include `perf60_stamps`, `perf60_isp_pipes`, `render_user_skip_empty_tiles`, `gpc_any_pstate` and
    `boot_gpu_perf`.
- Payload `build/boot/m1n1-linux-perf60cms-294091ddb3.bin`: **`357e89da6f74…`**.
- Entry `perf60cms-294091ddb3` (`build/gpu/perf60/perf60cms/`, release7's layout incl. `cmdline-sd`, `labwc/` and `entries.env`; the self-checks passed).
- **Run:**
  - Hop with the clock lane's runner and its perf60cm tuple:
    `PERF60_CLOCK_PKG=build/gpu/perf60/perf60cms scripts/gpu/perf60-clock-device.sh hop 100` (the bell/never-park parameters as that lane flew
    perf60cm).
  - Then fixture v6 (`build/gpu/perf60/perf60-fixture6.tar.gz`
    `b6cac011e5c3…`) with
    `perf60-ab-device.sh stamps:perf60_stamps=1`.
  - Read the stamps with §9.8.3; `perf60-summary.py` prints them per rung.
- The release7 worktree was `make clean`ed and is back on `a9/release7@802a3d4fc4`, clean. This lane created no
  separate perf60-* worktrees.

### 9.4 Quickshell redraws its three windows at the compositor's rate (2026-11-03)

- **Device (`dmg93.txt`):** every ~385 ms the bar (768×30), the dock (768×245) and **`omarchy-background` (768×1024)**
  commit full-surface damage together. Hyprland's full-panel passes follow from that.
- **Mechanism (Qt, inferred):** Qt Quick's GUI-thread ("basic") render loop re-renders *every* window on each
  animation tick while any animation runs, and Qt Quick damages the whole surface on every frame. The ticks are paced
  by Hyprland's frame callbacks (~2.6 Hz here). The threaded loop keeps a window's animation to that window.
- **Shell QML** (`build/gpu/perf60/omarchy-shell/shell`, from the rootfs; the always-visible windows):
  - every infinite animation is gated. `Style.reduceMotion` (= Hyprland `animations:enabled` false, true here) gates
    the button spinners, the MultiSelect spinner and the media title scroll (also gated on a playing track). The dock's
    launch pulse (`DockWindow.qml:514`) runs while `Dock.isLaunching(key)`, with a 10 s `launchTimeout`.
  - The `FrameAnimation`s in `Background.qml:364`, `BackgroundIntro.qml:258/315` stop after two frames. `Bar.qml:1151`
    runs only during a drag.
  - So the redraw is either a gated animation stuck on, or the basic loop amplifying any tick.
- **Live test** (owner session, foot blinking; the `Damage:` log as in §9.3, 10 s each):
  1. **Render loop:** restart the shell with Qt's logs:
     `pkill -x quickshell; QSG_INFO=1 QT_LOGGING_RULES="qt.scenegraph.renderloop.debug=true" systemd-cat -t omarchy-shell -- quickshell -n -p /usr/share/omarchy/shell &`
     (as linux, in the session env).
     - `journalctl -t omarchy-shell | grep -iE 'render loop|basic|threaded|animation'`.
     - If the 2.6 Hz commits are gone after the restart, the cause was a stuck state (the dock's launch, a spinner) and
       the journal says which loop.
  2. **Threaded loop:** the same restart with `QSG_RENDER_LOOP=threaded` added. If the background's 768×1024 commits
     stop while the bar or dock keep animating, the basic loop is the amplifier.
  3. **Bisection:** `omarchy-shell shell hide omarchy.dock` (then `show`). If all three stop, the dock's animation is
     the source.
- **Fixes, by outcome:**
  - basic loop amplifying: `QSG_RENDER_LOOP=threaded` in the shell's launch env (`omarchy-launch-shell`), if the
    threaded loop is clean on our Zink/WSI path (the qs ladders ran threaded? to verify);
  - a stuck gated animation: the QML condition (Omarchy's code);
  - Qt redrawing without a QML cause (frame-callback/release pattern from our WSI): `QSG_RENDERER_DEBUG=render`
    shows renders with nothing dirty, then our WSI is the next look.

### 9.5 The stuck redraw and the basic-loop amplifier (2026-11-03)

- **Device (`q94.txt`):**
  - the long-running shell commits dock, bar, background (768×1024) and notifications (465×1024) at ~2 Hz;
  - a relaunched shell is quiet (1 box / 10 s), with the default loop or `QSG_RENDER_LOOP=threaded`;
  - `shell hide omarchy.dock` repaints background + bar every frame (~4 Hz) while the dock animates.
  - So a state the long-running shell gets into is the trigger, and the basic loop is the amplifier.
- **Ruled out statically** (the always-visible windows):
  - the dock's launch pulse: `Dock.qml` settles launches on a 1 s timer with a 10 s timeout;
  - the toast countdown: `Toast.qml` ticks every 100 ms only while `ticking`, which is false when paused or for a
    persistent notification, and expires;
  - the battery service: 30 s;
  - the reduceMotion-gated spinners and scroll: animations are off;
  - the two-frame `FrameAnimation`s.
  - The dock's own Behaviors (tuck 180 ms, shift 150 ms, scale 120 ms) are finite, but would sustain a storm if a layout
    feedback keeps re-triggering one. Not provable statically.
- **Live bisection in the stuck state** (before any restart; the `Damage:` log as in §9.3, 10 s per step):
  1. `hyprctl layers`, a scanout screenshot, `qs ipc -n -p /usr/share/omarchy/shell show` (the live IPC targets).
  2. `omarchy-notification-dismiss` (all). If the storm stops, a toast's animation (a fade re-triggered by a re-posted
     notification) is the trigger: `journalctl -t omarchy-shell` around it shows who posts.
  3. `omarchy-shell shell hide omarchy.notifications`, then `omarchy-shell shell hide omarchy.bar`, each followed by
     `show`. The surface whose hide stops the others' commits after its hide animation ends holds the running animation.
     The dock was hidden already: the storm got faster during the hide and is not ruled out after it.
- **Amplifier test:** relaunch with `QSG_RENDER_LOOP=threaded` (as in §9.4), then `omarchy-shell shell hide omarchy.dock`.
  Pass = only the dock commits during the hide, and the background and bar stay quiet.
- **Fix, prepared in our layer** (`scripts/omarchy/rootfs/hypr/ipad.lua`, uncommitted; deploy with `hot-apply.sh` only
  after the amplifier test passes): `hl.env("QSG_RENDER_LOOP", "threaded")` before the shell starts. It covers both
  `start-hyprland` and uwsm sessions. `/usr/share` is untouched.
- **Noted:** `uwsm-env-ipad` still exports `QT_QUICK_BACKEND=software` (the llvmpipe era). In a uwsm login the shell
  then renders with Qt's software backend, not on the G5P. The runner's `start-hyprland` sessions do not source it.
  That needs a decision for the GPU desktop.

### 9.6 Qt Quick on GL vs Qt's software renderer on the GPU desktop: the A/B (prepared 2026-11-03)

- **Decision (orchestrator):** `QT_QUICK_BACKEND=software` moves into the llvmpipe branch of `uwsm-env-ipad`.
- **Prepared** (`scripts/omarchy/rootfs/hypr/uwsm-env-ipad`, uncommitted, not deployed): the GPU branch reads
  `qt_quick=` from `~/.local/state/linux-a9/display`. `gl` (default) unsets `QT_QUICK_BACKEND`; `software` exports it.
  The llvmpipe branch keeps `QT_QUICK_BACKEND=software`.
  - Checked with a fake render node: gpu → unset (an inherited value is cleared too), gpu + `qt_quick=software` →
    software, gpu + `qt_quick=gl` → unset, software renderer → software (+ `LIBGL_ALWAYS_SOFTWARE=1`).
  - Whichever arm wins becomes the GPU default by one word (`_a9_qtquick=gl` → `software`).
- **A/B** (after the §9.5 bisection and amplifier test; owner session through the runner, which does not source
  `uwsm-env-ipad`, so the arm is set in `EXTRA_ENV`; foot blinking, then es2gears; 10 s per measurement):
  - **GL:** `EXTRA_ENV="PVR_G5P_PASS_LOG=1"` (+ `QSG_RENDER_LOOP=threaded` if §9.5 passed).
  - **software:** `EXTRA_ENV="PVR_G5P_PASS_LOG=1 QT_QUICK_BACKEND=software"` (+ the same loop setting).
  - Measure per arm:
    - es2gears FPS;
    - Hyprland slots 8/7 jobs/s and 3D median;
    - the quickshell process CPU %: `top -b -d 10 -n 2 -p $(pgrep -x quickshell) | tail -1`;
    - `Damage: Box` lines per 10 s and their sizes, idle with foot blinking;
    - pass-log `tiles=` per pass.
  - **Pick:** the arm with the lower Hyprland 3D median and the smaller damage at idle, unless its CPU % costs more
    frames than it saves (gears FPS decides a tie).
- **Deploy** (both files, after the A/B): set the GPU default to the winner, then `scripts/omarchy/hot-apply.sh`
  (`ipad.lua` with `QSG_RENDER_LOOP=threaded` if §9.5 passed, `uwsm-env-ipad` → `~/.config/uwsm/env.d/90-ipad`).
  The stuck-state fix applies either way.

#### 9.6 result (release7, package-dbg, owner session through the runner, 2026-11-03)

| | GL (`PVR_G5P_PASS_LOG=1`) | software (`+ QT_QUICK_BACKEND=software`, checked in quickshell's environ) |
|---|---|---|
| runner flips/s | 3.3 | 5.5 |
| idle, foot blinking: Hyprland 8/7 | 17.1 jobs/s, 3D median 35.9 ms | **0 GPU jobs in 10 s** |
| idle: quickshell 10/9 | 5.6 jobs/s, 16.7 ms | 0 |
| quickshell CPU at idle | n/a | 0.2 % |
| es2gears | no FPS line (8/7 at 2.0 jobs/s; windowed GL gears tonight 2–3 FPS) | **8.37 / 8.43 FPS** (8/7 15.5 jobs/s at 36.6 ms, 10/9 7.8/s at 5.2 ms) |

- The GL arm's damage/tiles histograms are invalid (the window offsets read the whole log). They still show the storm
  boxes 768×30 / 768×1024 / 768×245 / 465×1024 and mostly `tiles=3072/3072`.
- The software arm's numbers were taken by hand (`build/gpu/perf60/q96b.txt`): the q96 measure script hung twice on a
  bare `wait` that also waited on the endless foot job.
- **Decision (orchestrator): software wins.** `uwsm-env-ipad`'s GPU branch now defaults to `qt_quick=software`
  (`gl` still selectable in `~/.local/state/linux-a9/display`). The shell is CPU-rendered with partial damage;
  Hyprland still composites every surface on the G5P. The `QSG_RENDER_LOOP=threaded` line in `ipad.lua` stays
  commented out until it is tested on the device.
- Open, on the shell side: the stuck-state ~2 Hz tick and the 7.4 Hz bar animation after a respawn (§9.5) still
  exist. With software they no longer cost GPU jobs, but they do cost a small partial-damage Hyprland repaint.

## 11. Hyprland at 60 fps on release8: what bounds a frame, and the cuts (2026-11-03, offline)

### 11.1 The baseline, corrected [V]

- **"flip-rate 4.1–4.6/s" is not a frame cost.** `hypr-stage2.sh`'s `flip-drive` switches workspace every 0.7 s with
  animations off (`hyprctl dispatch … focus workspace; sleep 0.7`), and the proof divides completions by the window:
  38 flips / 18 dispatches ≈ 2 frames per switch. It measures the script's pacing.
- **The end-to-end number to use is gears windowed: 33–35 FPS** (`r8b/run.txt`, `importfix/run.txt`). gears covers
  ~90 % of the panel, so every Hyprland frame is a full-damage frame. That is ≈ 29 ms per gears → Hyprland → flip
  cycle, i.e. two vblanks. Hyprland's own frame cost is the open quantity; §11.4 measures it.
- **Per-job GPU time on never-park is small:** on the release7 never-park run (`stage4/dmesg-cdefer.txt`, 11,897
  jobs), TA publish→done 2 ms median, 3D publish→event 1–3 ms, the whole job to the host's done 4–6 ms. After
  memclk, full-panel blit 3D ≈ 4 ms, clear ≈ 2 ms (§10.3). **So a 16.7 ms frame is bounded by latency and job count,
  not fill.**

### 11.2 One Hyprland frame on release8, decomposed [V code, I sizes]

Owner session: frozen ICD `g5p-hypr-s1fix@0a4cdcd8541`, no `PVR_G5P_FOLD_CLEAR` (`hypr-s2.session.env`:
`QT_QUICK_BACKEND=software` only), release8 kernel (none of the perf60 fill commits: no skip-empty contract, no
`perf60_poll_us`).

1. **Hyprland always renders into a work buffer and copies it to the swapchain.** `CHyprOpenGLImpl::begin()` binds
   `getUnusedWorkBuffer()` and sets `m_offloadedFramebuffer = true` unconditionally. `end()` copies with
   `renderTexturePrimitive` into `outFB` (Hyprland 0.56.2 `src/render/OpenGL.cpp:753-760, 773-812`). No config turns
   that off. So there are **two full-panel passes per full-damage frame**.
2. **The work buffer's clears add a third GPU job.**
   - `clearAfterInvalidation()` (a full clear) is the pass's CLEAR load. The per-damage background clears follow as
     partial `vkCmdClearAttachments` before any draw.
   - Our ICD cannot draw a clear rectangle. So `clear_split()` ends the still-empty pass and runs it as a full-panel
     **CLEAR_ONLY job**, does the rectangles as **CPU** ops, and continues the scene as a LOAD job (§9.1; offline:
     `offline/small-*`).
   - Without fold-clear (the owner session), that is a whole GPU job per frame: 3072 tiles stored, TA + 3D + two
     completion detections.
3. **Every job's host side is synchronous** (`typed_submit`: ioctl → `wait_job` → TO_CPU, `g5p_drm_render.c`):
   - the per-job arena copies: before this change, 1.4 MB copied or zeroed per job (pool7 768 KB, pool8 512 KB, user
     128 KB) plus their `TO_DEVICE`;
   - `TO_DEVICE` of every referenced BO, whole: allocations ≥ 4 MiB are dedicated BOs (a 12.6 MB framebuffer is
     12.6 MB). Smaller ones (uniforms, vertices, small textures) are slices of 64 MiB arena chunks, and a chunk syncs
     whole;
   - the kernel's `ACCESS_CACHE` whole-BO maintenance of every shared dma-buf (scanout, client surfaces), both ways;
   - `TO_CPU` of every written BO, whole.
   - The kernel's `BO_SYNC` takes `offset`/`size` but syncs the whole BO ("allowed to be stronger"), and the ICD
     always asks for the whole BO.
   - Upper bound from the fixture on never-park: job wall − (TA + 3D) ≈ 0.8 ms for a 1-draw job, including one chunk
     and two 12.6 MB syncs. So syncs are not ruinous per job, but they add up over three jobs and the CPU ops.
4. **The kernel's completion detection sleeps 1–2 ms per RAM sample** (`g5p_l123_pause`: `usleep_range(1000, 2000)`,
   still in `a9/release8`).
   - On never-park the host gaps per job are ≈ 1 ms (`stage4`: slot 8 TA 2 + 3D 1 vs done at 4; slot 10 2 + 3 vs 6),
     plus the TA-side detection round 1 measured (`ta_ev` 7.9 → 7.2 ms at 100 µs; tail 1.0 → 0.07 ms, §8.1).
   - So the recoverable latency is ~1.5–2 ms per job, ~5 ms per 3-job frame [I from those numbers].
5. **The chain is serial:**
   - gears submits and waits;
   - Hyprland's frame runs three synchronous jobs plus CPU ops;
   - then the commit;
   - then the flip on the next vblank.

   Estimated Hyprland frame: 3 × (TA 2 + 3D 2–4 + detection ~1–2 + ICD ~1) ≈ 18–27 ms. That matches two vblanks
   (33–35 FPS). [I; §11.4 measures it.]

### 11.3 Cuts, ranked by expected ms per full-damage Hyprland frame

| # | cut | where | saves / frame | scales with clock? | state |
|---|---|---|---|---|---|
| 1 | completion detection by event, not by 1–2 ms sleeps (wake the phase wait from the firmware-event IRQ path; at least `perf60_poll_us`-class short sleeps) | **kernel (ask)** | ~3–5 ms (3 jobs × ~1.5 ms) | **no**: pure latency, grows in share at 723 MHz | release8 lacks it; `a9/perf60-fill`'s `perf60_poll_us` is the measured interim (§8.1) |
| 2 | clear rectangles drawn on the GPU inside the pass (clear quads), so the empty CLEAR_ONLY job and the CPU rectangle memsets disappear | ICD (Mesa) | one whole job: ~5–7 ms (TA 2 + 3D ~2 + detection ~3) | partly (the 3D part) | **specified (§11.5), not built** |
| 2′ | interim A/B: `PVR_G5P_FOLD_CLEAR=1` (already in the frozen ICD) trades that GPU job for CPU memsets of 12.6 MB + whole-BO syncs | ICD env | ± (GPU job ~5–7 ms vs CPU ~3–5 ms) | no | **runnable now** (§11.4 arm B) |
| 3 | two passes are structural in Hyprland 0.56.2 (work buffer + copy). Rendering straight into `outFB` when nothing needs the offload (no blur, no CM, no mirror, no screen shader, zoom 1) | Hyprland (source patch, userspace rebuild) | one full-panel pass: ~5–8 ms | partly | not started; needs a device Hyprland build |
| 4 | per-job arena upload: only the bytes the job can read | ICD | ~1.4 MB copy+clean per job → ~0.3–0.6 ms/job, ~1–2 ms/frame | no | **built** (`g5p-perf60-hypr@9c40c79bfd1`) |
| 5 | cache maintenance by range and only where the CPU can see the memory (TO_CPU at map/invalidate for non-host-mapped memory; range syncs of arena slices; kernel honouring `offset`/`size`; `ACCESS_CACHE` only where a CPU writer or reader exists) | ICD + **kernel (ask)** | measured by §11.4's `passt` `pre`/`post`/`shared` columns | no | instrumented; built after the numbers |
| 6 | asynchronous submit: return after the ioctl and wait on the job's syncobj only when needed, so Hyprland's CPU and the GPU overlap | ICD (+ kernel queue depth) | the CPU share of a frame (cuts 2–5) moves off the critical path | no | spec only: needs 5 first (no post-job TO_CPU on the critical path), and the kernel's per-context queue depth (the ICD's `accepted` latch) |
| 7 | TA's ~2 ms fixed cost per job | firmware | 3 × 2 ms | partly | firmware-internal (§8.1) |

- **At 723 MHz** the GPU parts (3D, part of TA) shrink by ~2.1×. Items 1, 2′, 4, 5 and 6 do not change, so they become
  the larger share.
- **Cuts 1 and 2 are co-equal at ~5 ms each.** Cut 1 is the biggest clock-independent cut, and it is not Mesa's.

### 11.4 DEVICE-READY: ICD package `perf60h` (release8, owner session, labwc untouched)

- **ICD** `g5p-perf60-hypr@9c40c79bfd1` (Mesa private fork, `Generated-by: LLM`): release8's userspace tip
  `g5p-hypr-s1fix@0a4cdcd8541` + `g5p-perf60-empty` (skip-empty: inert on release8, no cap 32; `PVR_G5P_PASS_LOG`)
  + the per-pass cost log and the upload trim.
  - `libvulkan_g5p.so` `556adb4580a2…`.
- **Gates:** `HYPR_LANE=perf60h hypr-gpu.sh regress` against the frozen release8 ICD (`2b15982e`): **270/270
  compiles identical, every gfx-test scene identical in 4 orders** (`build/gpu/perf60/perf60h-build.log`). Offline
  stage, Hyprland run, qs-ladder and blend-ladder: §11.6.
- **Package:** `build/gpu/hyprland-gpu/perf60h/s2package/` (sha256 in §11.6).
- **Arms** (each: hop/session as release8's runner does, gears windowed for the FPS, 10 s of `G5P` lines):
  *(Device/host command block omitted; it targets the private workspace.)*
- **Read:**
  - per pass shape: `wait` (GPU + kernel detection + the kernel's `ACCESS_CACHE` for_cpu sync of shared BOs) against
    `up+pre+build+ioctl+post` (ICD CPU; `ioctl` includes the kernel's for_device sync of shared BOs);
  - `CLEAR_RECTS` ops: the CPU clears;
  - jobs per frame = passt lines per Hyprland frame;
  - gears FPS is the end-to-end figure.
  - Optionally Hyprland's own frame timer: `hyprctl eval 'hl.config({ debug = { overlay = true } })'` and a screenshot
    (the overlay costs a draw; screenshot only).
- **Pass criteria:**
  - A: no `RENDER-V3 terminal`/fault/`GPU-RECOVER`; the desktop renders as on C (scanout screenshot); gears FPS ≥ C's
    (33–35).
  - `passt` lines present. The upload trim must show `up` ≈ 150 kB per job (seven 16 KB arenas + scratch 32 KB always
    whole, plus the used pool8 entries and user bytes) instead of ~1.5 MB.
  - **The trim has no env gate.** Arm A is both its measurement and its proof. If blend-ladder's scissored or `ds_*`
    rungs, or the fill-ladder's `fill_load_scissor`, fail on the perf60h ICD, revert `9c40c79bfd1` (one commit;
    the log goes with it).
  - B: the same, plus no `clear_only=1` passes; compare gears FPS and Hyprland jobs/s with A.
  - Correctness of the trim: `blend-ladder-device.sh` (scissored draws, the `ds_*` depth rungs) and the fill-ladder's
    `fill_load_scissor`/`fill_load_small` on the perf60h ICD, all PASS.

### 11.5 Spec: clear rectangles on the GPU (cut 2)

- **Where:** `g5p_CmdClearAttachments` → `clear_split()` today. Instead, for colour attachments in a single-target or
  MRT pass, record each rectangle as a draw in the current job:
  - an internal pipeline: VS = the rectangle's corners from a 4-vertex strip in the user arena (or `gl_VertexIndex`
    with the rect in push constants), FS = a constant colour from a uniform, no blend, colour write mask = the
    attachment, no depth/stencil test;
  - scissor = the rect.
- **Apple and upstream:** pvr's `pvr_clear.c` draws clear rectangles as an index-list/rect primitive with a constant
  colour, and sets `process_empty_tiles` only when the background clears (§7). Apple's mid-pass clears are draws too
  [I] (its clear USC is the background program; a mid-pass clear has no other form on TBDR).
- **Effect on Hyprland's frame:** the work buffer becomes one GPU job: CLEAR background (full clear) + rectangles +
  scene. No empty job, no CPU memsets, no whole-BO syncs for the rectangles.
- **Rungs:** blend-ladder `clear_mid_*` (already 59/59 with the split), qs-ladder `load_blend`, and new
  `clear_rect_first`/`clear_rect_after_draw` (rects of two colours over a pattern, pixel-exact, with and without a
  CLEAR load).
- **Scale:** an internal pipeline through `g5p_compile_graphics` (NIR built in the ICD), a small vertex buffer per
  rect batch, and the recorder's existing draw path. Estimated 400–600 lines with tests. For the Mesa lane (routing:
  Codex), or the next round here.

### 11.6 Build record

- **Branch** `g5p-perf60-hypr` (worktree `build/third_party/mesa-a9-perf60-src`):
  - `c9e80850d2c`: merge of `g5p-perf60-empty` onto `g5p-hypr-s1fix@0a4cdcd8541`, no conflict;
  - `9c40c79bfd1`: the pass-cost log and the upload trim.
- **Built** in s1fix's configured tree like perf60e (`HYPR_LANE=perf60h scripts/gpu/hypr-gpu.sh build`, new lane;
  the s1fix worktree was switched back to `g5p-hypr-s1fix@0a4cdcd8541` afterwards, clean).
- `libvulkan_g5p.so` `556adb4580a2…`.
- **Gates** (`build/gpu/perf60/perf60h-build.log`, `perf60h-pkg.log`):
  - regress against the frozen release8 ICD `2b15982e`: 270/270 compiles identical; gfx-test default 126/0,
    depth+gles3tex+textypes+varyings 119/0, gles3tex+varyings 84/0, vk10+cts1 46/0 (each +1 for the merged
    skip-empty scene); 4588 scene files identical in 4 orders;
  - offline Hyprland on the fake node (`hypr-gpu.sh offline`, new-stage1): 8481 submits, 0 refused, refusals = the 2
    D32F format queries the base also has;
  - qs-ladder offline PASS, blend-ladder offline PASS (both through the real typed transport, so the trimmed
    `upload()` ran).
- **R8_HYPR_PK package** (`HYPR_LANE=perf60h HYPR_S2_PK=build/gpu/hyprland-gpu/perf60h/s2package scripts/gpu/hypr-stage2.sh package`):
  `build/gpu/hyprland-gpu/perf60h/s2package/hypr-s2-a9.tar.gz`
  **`df6df2da5ad9…`**, MANIFEST
  `mesa=g5p-perf60-hypr@9c40c79bfd1`. The arms in §11.4 use `R8_HYPR_PK=build/gpu/hyprland-gpu/perf60h/s2package`.
- **Tools:** `scripts/gpu/perf60-passt.py` (summary of the `passt`/`cpuop` lines; self-tested on sample lines).
  `hypr-gpu.sh` has lane `perf60h`; `hypr-stage2.sh` names its branch.
- **Arm B also runs on the frozen package:** `R8_EXTRA_ENV="PVR_G5P_FOLD_CLEAR=1"` without the log, for an FPS-only
  A/B against C.
- **Cross-lane note:** `mesa-a9-hyprs1fix-v1/out` and `/install` now hold the perf60h build. The release lane runs
  `HYPR_LANE=s1fix scripts/gpu/hypr-gpu.sh build` before any s1fix `stage`. `hypr-stage2.sh package` also refuses a
  stage whose ICD is not `bin/new`'s.
- **Kernel asks for release8** (not this lane's code): cut 1 (event-driven completion detection, or at least the
  short-sleep wait), and in cut 5 the `BO_SYNC` range plus the `ACCESS_CACHE` policy.

### 11.8 Cut 3 (Hyprland renders straight into the swapchain): feasibility, plan, estimate (not built)

**Can we build a patched Hyprland 0.56.2 offline? Yes, with care [V inventory].**
- **What the owner runs:** Omarchy's `hyprland 0.56.2-7` (`omarchy` repo, `/usr/bin/Hyprland` sha256 `a9e57097…`)
  against `aquamarine 0.15.1-1.3`, `hyprutils 0.14.2-1`, `hyprlang 0.6.8-5`, `hyprgraphics 0.5.1-4`,
  `hyprcursor 0.1.13-7` and `hyprwire 0.3.1-3` (`build/omarchy/reports/packages.txt`).
- **The image `linux-a9-hypr-run:dev`** (ALARM aarch64, native arm64 on this Mac) has 0.57.0's libraries
  (hyprutils 0.14.3) plus the device's 0.56.2-7 binary, aquamarine and hyprutils in `/opt/dev`
  (`hyprland-gpu.md` §3). It has no build tools: no cmake, ninja, meson or hyprwayland-scanner.
- **Source:** `build/omarchy/rotation-src/Hyprland` is a clean v0.56.2 checkout.

**Plan:**
1. **Build image** `linux-a9-hypr-build` FROM `linux-a9-hypr-run:dev`:
   - pacman: `cmake ninja meson hyprwayland-scanner hyprland-protocols glaze pkgconf` and the dev headers of
     libinput, re2, muparser, tomlplusplus, libdrm, pixman, wayland-protocols, xcb (as 0.56.2's CMakeLists asks);
   - **pin the device ABI:** build hyprutils 0.14.2, aquamarine 0.15.1 and hyprwire 0.3.1 from their tags into a
     prefix (or install the device's exact `.pkg.tar.zst` from `live-pkgs` / the ALARM archive), so the binary links
     against the libraries the rootfs has. hyprlang, hyprgraphics and hyprcursor already match.
2. **Reproduce Omarchy's build:** fetch the `omarchy` repo's PKGBUILD for 0.56.2-7 (flags, any patches). Build it
   unpatched first and **compare**: same exported symbols and NEEDED libraries, and, if the build is reproducible
   enough, the same `.text` size class. This proves the toolchain before any change.
3. **The patch** (`src/render/OpenGL.cpp` `begin()`/`end()`, about 100–200 lines). Render directly into `outFB` and
   skip the offload + copy only when every one of these holds; otherwise keep today's path:
   - no blur pass this frame (`decoration:blur:enabled` off, or no blurred surface/layer visible);
   - no screen shader (`m_finalScreenShader` empty) and not `crashingInProgress`;
   - no colour management (`NEEDS_CM` false: the monitor's image description equals the main FB's) and no FP16/10-bit;
   - not mirrored and no copy-FB consumer (`needsACopyFB()`, `needsUnmodifiedCopy()`: screencopy, mirrors);
   - mouse zoom factor 1 and not a fake frame (`fb` given: screencopy of a region);
   - `m_renderMode == RENDER_MODE_NORMAL`.
   - **Damage:** rendering straight into a swapchain buffer must cover what that buffer's age requires: use
     `finalDamage` (the ring-accumulated damage for this buffer's age), not the frame's own damage, for the scissor,
     and drop the work buffer's full `clearAfterInvalidation()`.
   - `mainFB`/`currentFB` must point at `outFB`, so effects reading the main FB still work.
4. **Offline proof** (`scripts/gpu/hypr-offline.sh` on the fake node, ICD with `PVR_G5P_PASS_LOG=1`):
   - one pass per frame (no scanout-copy pass) with blur off;
   - two passes when blur, or a screen shader, is switched on live (fallback);
   - same refusal count, no assertion.
   - A config matrix: blur on/off, screen shader, mirror output (a second headless output), screencopy (`grim` in
     the container).
5. **Device:** the runner deploys the binary beside the stock one (e.g. `/usr/local/bin/Hyprland-perf60`, started
   by `start-hyprland` through an env override). `/usr/bin` stays untouched. Arms: gears FPS and the pass log against
   the stock binary.

**Estimate:**
- build image with pinned ABI: 2–4 h (version pinning is the risk);
- reproducing Omarchy's 0.56.2-7 and checking it: 1–2 h;
- the patch: 2–3 h;
- offline matrix: 2 h;
- in all about 1–1.5 working days.
- **Saves** one full-panel pass per frame (~5–8 ms on release8; with cut 2, the work buffer's clears go away too,
  because the swapchain buffer needs only its aged damage redrawn).
- **Risk:** ABI drift against the rootfs libraries (mitigated by step 1's pinning and step 2's comparison); behaviour
  differences in effects that read the main FB (covered by the fallback list).
- **Waiting for the orchestrator's go before building.**

### 11.9 Cut 5, ICD half: cache maintenance by range (built on `g5p-perf60-sync@139fe06c167`, merged into the package after cut 2)

- **Every `BO_SYNC` now names a GPU VA range**, intersected with each kernel BO behind the memory:
  - a job's TO_DEVICE/TO_CPU: the span of the memories it references in that BO (`g5p_job_resource.lo/hi`, from
    `add_resource()` and the xfb staging path);
  - flush/invalidate: the app's ranges;
  - CPU copy ops: their memories' slices;
  - xfb: the buffer's range.
  - Parts of a spanned BO outside the range are skipped. Shared dma-bufs stay kernel-managed (`ACCESS_CACHE`).
  - `passt` counts the bytes requested.
- **Effect on release8: none yet.** Its kernel validates `offset`/`size` and syncs the whole BO. The win arrives with
  the kernel lane's range sync (cut 5 kernel half). Biggest case: a 64 MiB arena chunk synced for small uniform or
  vertex slices on every job.
- **Not done (device-measured):** narrowing *which* syncs happen, i.e. no post-job TO_CPU for memory the CPU never
  maps (moved to map/invalidate time). Its size needs §11.4's `passt` `pre`/`post` columns. It is also the
  prerequisite for asynchronous submit (cut 6).
- Ranges are intersections with the BO, so they are valid by construction. The kernel rejects an out-of-range request
  with EINVAL, and offline the fake node accepts any `BO_SYNC`, so the device proof is arm D's clean run.

### 11.10 Clear quads (cut 2): build record

Built by Claude (Opus), offline only, 2026-11-03. Implements §11.5.

- **Commits** on `g5p-perf60-hypr` (private Mesa fork, `Generated-by: LLM`, not pushed), on top of `139fe06c167`:
  - `48677097ddc` g5p: vkCmdClearAttachments as clear quads inside the current job;
  - `3f155724abc` g5p-gfx-test: clearq scenes; cts1 pins the split path;
  - `09b21fbb143` g5p: BO_SYNC ranges in whole GPU pages. This fixes `139fe06c167` (cut 5, §11.9), not cut 2;
    see "Cut 5 finding" below;
  - `842c982ac00` g5p: a pass that ends without a draw is CPU clears, not a GPU job (owner's scope addition);
  - `f70ab5bf8c9` g5p-gfx-test: emptyq scenes; other groups keep draw-less GPU jobs;
  - `bc82302f291` g5p: draw-less passes into dma-buf memory keep their GPU job.
- **Files:** `src/imagination/vulkan/g5p/g5p_clear.c` (new: pipeline cache), `clear/clear.vert`,
  `clear/clear{1,2,4}.frag`, `clear/gen-spv.sh` (regenerates `g5p_clear_spv.h`), `g5p_cmd_gfx.c` (`clear_quads()`,
  `job_draw()`), `g5p_gfx.h`/`g5p_job.h`/`g5p_device.c`/`meson.build` (cache, `clear_draws`), `g5p_drm_render.c`
  (pass log), `g5p_submit.c` (trace JSON), `g5p_gfx_test.c`. Workspace: `tools/mesa-a9-hyprland-gpu/blend-ladder.c`.

**Design as built**
- **When:** `g5p_CmdClearAttachments` keeps the background path for a full-target clear before any draw in a
  full render area (`g5p_job_clear` / `g5p_job_clear_ds`, unchanged). Everything else (a partial rectangle, a clear
  after a draw, any clear in a partial render area) goes to `clear_quads()`: draws in the current job. No split, no
  CPU op, no CLEAR_ONLY job.
- **Shaders:** the ICD's compiler only takes SPIR-V, so these are embedded SPIR-V from GLSL (glslang 11:16.6.0).
  - The VS makes two triangles, (TL TR BR) (BR BL TL), from `gl_VertexIndex` 0..5. The rectangle (NDC) and depth
    come from push constants 0..19. The code is straight-line float: `right = |f-2| < 1.5`, `low = |f-3| < 1.5`.
    The compiler refused the first form, `i == 1 || i == 2 || ...`, with "vertex: ior".
    Compiled: general path, 8 temps, push upload 5 dwords → common 2, evidence `vs_alu select flatten`, 262 B.
  - The FS for 1, 2 or 4 targets outputs `o_k = color_k`, the colours at push 32 + 16k. All of them compile with
    keys `k0`/`last-read`. With `--mask 0` the program is empty (`0080`).
- **Pipelines** (`g5p_clear.c`): created through `g5p_CreateGraphicsPipelines` itself, with the pass's own
  dynamic-rendering formats. Settings: triangle list, no cull, blend off, no vertex input, and dynamic viewport,
  scissor and stencil reference.
  - Colour: every target has write mask 0xf; no depth or stencil test.
  - Depth/stencil: colour write mask 0, which disables tag writes (`isp_words` no_colour). Depth is ALWAYS + write
    at the quad's z, which is the clear depth. Stencil is ALWAYS/REPLACE ×3 with masks 0xff.
  - Cache: a per-device list keyed by {colour formats, target count, depth/stencil formats, aspects}, under a mutex.
    A refusal is cached too. The pipelines are destroyed in `g5p_DestroyDevice`.
- **Recording:** one draw per rectangle per group. All named colour targets form one group (a single emitpix writes
  every target); the depth/stencil aspects form the other.
  - Viewport = the whole attachment, so `vp` has no G5P_EV_VIEWPORT.
  - Scissor = the rectangle clipped to the render area. The app's scissor does not apply to
    `vkCmdClearAttachments`.
  - Push constants: the NDC rectangle, the depth and the colours.
  - Draws go through `job_draw()`, the split-on-full logic factored out of `draw()`.
- **No save/restore is needed.** `g5p_job_draw()` takes the bound state as arguments and re-emits every piece of it
  per draw; the only per-job cache is the placed programs, keyed by pipeline. The clear passes its own
  `g5p_gfx_state` and `vk_dynamic_graphics_state`, so the app's pipeline, dynamic state, push constants, sets and
  vertex buffers are never touched. `clearq` scene 2 checks this: the app draw after the clear keeps its own 8×8
  scissor, and the job holds two pipelines.
- **Empty-tile rule:** clear quads are geometry. They add no evidence bits that the rule reads (`LOAD`, the ZLS
  enables), so a LOAD pass with clear quads still meets the rule, and tiles that no draw or quad covers are only
  loaded and stored. A CLEAR pass stays CLEAR (rule false). This is correct: a quad's tiles are marked by its region
  clip like any draw's.
- **Transform feedback / queries active:** supported, not refused. The quads are drawn with a state whose
  `xfb_active` is false, so they emit no XFB records or events and count in no stream query. Vulkan treats
  `vkCmdClearAttachments` as a clear, not a draw.
- **Refused by name, then `clear_split`** (which refuses again whatever it cannot split):
  - profile1 placement;
  - `baseArrayLayer`/`layerCount` other than 0/1;
  - a subset of an MRT pass's targets (see below);
  - colour and depth/stencil aspects in one `VkClearAttachment`;
  - a depth/stencil clear without that attachment;
  - a refused pipeline (e.g. a depth/stencil quad in an MRT pass: write mask 0 with more than one target is
    refused by `validate_state`).
- **Knobs:** `PVR_G5P_CLEAR_QUADS=0` forces the old split (A/B, read at each clear; default on).
  `PVR_G5P_FOLD_CLEAR` stays the split's knob.
- **Logs:** `PVR_G5P_PASS_LOG` lines end with ` clears=N`; `perf60-passt.py`'s regex still matches. Job traces
  carry `"clear_draws": N` only when N > 0, so other jobs keep their bytes.
- **Blocker (MRT, one target):** a partial clear of only some targets of a 2- or 4-target pass has no quad form.
  One emitpix writes every target, and neither the MRT program set nor the compiler key has a per-target write
  mask (`validate_state` refuses one, and there is no N-target tile-read capture). An MRT pass also never splits.
  Such a clear is refused, as before. A clear of all targets in one call (Zink's `glClear` on an MRT FBO) is one
  quad writing each target's own colour.

**Draw-less passes (owner's addition; device arms A/B: 11–16 `load=0 clear_only=1 draws=0` jobs per log, each
~5–6 ms, alternating with the copy pass that samples them; neither `clear_split` nor FOLD reaches them)**
- At `vkCmdEndRendering`, a job with `draws == 0` is not submitted in these cases.
  - **CPU clear:** each colour target whose effective load op is CLEAR and that is stored gets a `CLEAR_RECTS` CPU
    op over the render area, in queue order. This is the mechanism FOLD and `vkCmdClearColorImage` already use.
    "Effective CLEAR" means the pass's load op, or a full `vkCmdClearAttachments` before any draw, which the
    background path turns into CLEAR. MRT targets are covered, each with its own colour. The clear values are
    copied as bits, so any format the CPU path packs works.
  - **Drop:** a pass with no such target (LOAD, DONT_CARE, a clear split's LOAD continuation) is simply dropped.
- **The GPU job stays** (existing path, not a refusal) for:
  - profile1 placement;
  - transform feedback events in the job, or an active query;
  - a depth or stencil aspect that is stored without being loaded. The ZLS planes are twiddled and opaque to the
    CPU, and the ICD has no CPU depth/stencil clear;
  - a target the CPU cannot clear (twiddled, a format without a CPU pack);
  - a target in dma-buf memory (exported or imported). The kernel maintains those caches only around GPU jobs and
    the ICD's BO_SYNC skips shared BOs, so a CPU write that no GPU job follows (a scanout) could stay in the CPU
    caches.
- **Knob:** `PVR_G5P_EMPTY_PASS_JOB=1` restores the GPU job (A/B); default is CPU.
- **Logs:** these passes print no `G5P pass` line. The CPU op prints `G5P cpuop kind=<CLEAR_RECTS> ...` under
  `PVR_G5P_PASS_LOG`, as for the fold.
- **Executor:** `CLEAR_RECTS` on linear images now fills one row and `memcpy`s it to the others, instead of one
  `memcpy` per pixel; the bytes are the same. Expected cost [I, from the coordinator's estimate]: ~0.4–0.9 ms CPU
  plus the image's sync, against ~5 ms for the job.

**Cut 5 finding (`139fe06c167`, found while gating this package; fixed in `09b21fbb143`)** [V kernel source]
- Every release8 kernel's `BO_SYNC` calls `g5p_bo_range_valid(offset, size, bo_size)` (`drivers/gpu/apple-g5p/
  drm-validate.h`), which requires `offset` and `size` to be multiples of `G5P_GPU_PAGE` = 16 KiB and returns
  EINVAL otherwise. This holds for `a9/release8` before and after its range commit `8ae02dbbb9`: the helper's body
  and its call in `g5p_bo_sync` are the same at `5cce71559a`, `01fb40e6c0` and `8ae02dbbb9`.
- `139fe06c167` sent the exact slice range: arena slices, app flush ranges, image sizes. The ICD fails the job or
  the flush on any `BO_SYNC` error, so on hardware nearly every job would have failed. §11.9's "valid by
  construction" covered only the bounds, not the alignment.
- The fake node accepts any `BO_SYNC`, so no offline gate could catch this. **Suggested:** make the fake node apply
  the kernel's rule.
- **Fix:** `g5p_drm_bo_sync_range` widens the intersection to the BO's whole 16 KiB pages and clamps it to the BO
  size. Syncing more is always allowed, and kernel BO sizes are whole pages (the whole-BO form passed before).
- **On a kernel that ignores the range** (`render_user_sync_range` bit 0 clear, release8's default), the request is
  now valid and the kernel syncs the whole BO: correct, as slow as before. With bit 0 set, the kernel syncs the
  page-widened range.
- `139fe06c167` caused no build error and no offline gate difference: regress is identical with and without it,
  and the offline gates below ran with it.

**Proof (offline; ICD `3d43fbf96504…` at `bc82302f291`)**
- **Shader compile check** (perf60h `g5p-shaderc`, keys default and `last-read`):
  - VS: general path, 8 temps, one push upload (5 dwords);
  - FS1/2/4: general, with `--mask 0` empty.
- **Regress** against `/tmp/perf60h-base` (the `9c40c79bfd1` build, ICD `556adb45…`):
  - **270/270 compiles identical**;
  - gfx-test default 126/0, depth+gles3tex+textypes+varyings 119/0, gles3tex+varyings 84/0, vk10+cts1 46/0, old
    and new alike;
  - **4588 scene files identical in 4 orders.**
- **Existing scenes are unchanged in bytes** because:
  - `cts1` runs with `PVR_G5P_CLEAR_QUADS=0`. Its pixel checks need the split's CPU rectangles, which the mock
    executes; GPU quads are not executed by the mock;
  - every group runs with `PVR_G5P_EMPTY_PASS_JOB=1`, so its draw-less scenes (clear-only, mrt2-clear-only, cts1's
    CLEAR continuation) keep encoding their GPU job.
- **Checks whose expectation changed** (no trace files involved):
  - depth group: "a depth clear after a draw" is now VK_SUCCESS (a quad). It is still refused with
    `PVR_G5P_CLEAR_QUADS=0`;
  - rejections: the three late, partial and render-area clears still succeed (now as quads; messages reworded).
- **New named groups** (`G5P_GFX_TEST_GROUPS=vk10,cts1,clearq,emptyq`): 48 PASS, 0 FAIL.
  - **clearq.** Each scene asserts one recorded job per pass and its draw and quad counts, the ISP scissor table
    (pool8), the evidence, and the push words found in the job's state/user arenas.
    - `cq-first`: CLEAR pass with 2 rects before any draw → 1 job, 2 draws = 2 quads, scissors = the rects, neither
      CLEAR_ONLY nor LOAD, the colour present.
    - `cq-after-draw`: LOAD pass, app scissor 8×8, draw, clear, draw → 1 job, 3 draws, 1 quad, 2 pipelines, scissor
      table [app, rect, app]. This proves the clear ignores and preserves the app's scissor.
    - `cq-two-colours`: 3 quads, 1 pipeline, both colours, and r1's NDC (−.5, −.75, .5, .25, 0) in the vertex words.
    - `cq-area`: a partial render area; the area clear was a split before and is now 1 quad scissored to the area.
    - `cq-depth`: LESS draw, depth rect clear to .25, LEQUAL draw → 1 job, 3 draws, 3 pipelines,
      (rect, .25) in the vertex words.
    - `cq-stencil`: a stencil-only rect clear to 7 on D32S8 → 1 job, STENCIL evidence from the quad alone.
    - `cq-mrt`: both targets in one call → 1 quad writing green and red; target 1 alone is refused by name.
    - `cq-knob-off`: `PVR_G5P_CLEAR_QUADS=0` brings back the split's CLEAR_ONLY job.
  - **emptyq.**
    - `ep-clear-sampled`: a draw-less CLEAR pass whose image the next pass samples → **1 job** (the sampling pass),
      and **every texel of the cleared image = 0xcc336699 exactly** (the CPU clear, run by the mock).
    - `ep-load-drop`: a LOAD-only pass → 0 jobs, pattern intact.
    - `ep-clear-attachments`: a full `vkCmdClearAttachments`-only pass → 0 jobs, every texel 0xffff0000.
    - `ep-mrt`: 2 targets → 0 jobs, each target's own colour exact.
    - `ep-depth-kept`: a depth CLEAR+STORE → its CLEAR_ONLY job, no CPU clear.
    - `ep-knob`: `PVR_G5P_EMPTY_PASS_JOB=1` → 2 jobs again.
- **tramp, stage:** PASS (stage: ICD `3d43fbf96504`, tramp `a73c82801529`, 6 clients).
- **Offline Hyprland** (`hypr-gpu.sh offline`, `HYPR_EXTRA_ENV=PVR_G5P_PASS_LOG=1`, 50 s, foot + weston-simple-shm):
  - new-stage1: **5640 submits, 0 refused**; refusals = the 2 D32_SFLOAT format probes (base has them too);
    2818 frames;
  - **0 render-pass splits, 0 `clear_only=1` passes.** Passes: 2819 LOAD (`clears=0`), and 2821 CLEAR passes
    carrying 1/3/5/6 clear quads (1953/5/5/856);
  - the cut-2-only build had 5788 submits; §11.6 recorded 8481 submits for `9c40c79bfd1` over the same 50 s run
    (indicative: the frame count is not fixed);
  - this workload makes no draw-less pass offline, so the emptyq scene and the blend-ladder rung cover that shape.
- **qs-ladder offline PASS; blend-ladder offline PASS (73 rungs, each `refusals=0`).**
  - New rungs: `clear_rects2_load`, `clear_rects2_clear`, `clear_rects2_mid`, `clear_rect_noclip`, `ds_clear_rect`,
    `empty_clear_sampled`.
  - All six record and submit with 0 refusals and 0 splits.
  - `empty_clear_sampled` under `PVR_G5P_PASS_LOG`: the default run has a `G5P cpuop kind=8` (CLEAR_RECTS, 131072 B
    = 256×128×4) where `PVR_G5P_EMPTY_PASS_JOB=1` has `G5P pass 256x128 load=0 clear_only=1 draws=0`.
  - Pixels are judged on the device only.
- **Package** (`HYPR_LANE=perf60h HYPR_S2_PK=build/gpu/hyprland-gpu/perf60h/s2package scripts/gpu/hypr-stage2.sh
  package`): `build/gpu/hyprland-gpu/perf60h/s2package/hypr-s2-a9.tar.gz`
  **`752721c7973b…`**, MANIFEST
  `mesa=g5p-perf60-hypr@bc82302f291`, icd `3d43fbf9…`. It carries cuts 2 and 4, cut 5's ICD half with the
  page-alignment fix, and the draw-less pass change.
  This exact package is rebuilt byte-identically in `perf60h/s2package-752721c7`. §11.11.3's package adds `bin/Hyprland-a9-direct`.
- **Release lane:** after the gates, `mesa-a9-hyprs1fix-src` is back on `g5p-hypr-s1fix@0a4cdcd8541` and the
  perf60 worktree on `g5p-perf60-hypr`. `HYPR_LANE=s1fix hypr-gpu.sh build` was rerun: rc 0,
  `commit=0a4cdcd8541`, ICD `2b15982e…`, the frozen release8 ICD again.

**Device rungs to fly** (pixel-exact on hardware; the knobs make every A/B one env change):
- blend-ladder `clear_rects2_load`, `clear_rects2_clear`, `clear_rects2_mid`, `clear_rect_noclip`, `ds_clear_rect`,
  `empty_clear_sampled`, together with the existing `clear_mid_*` and `clear_first_rects*`;
- Hyprland arm A on this package: expect no `clear_only=1` passes and no CPU `CLEAR_RECTS` damage memsets. Each
  work-buffer frame should be one CLEAR job with `clears=N`. The draw-less `C0 d0` passes should show up as
  `cpuop kind=8` lines;
- A/Bs: `PVR_G5P_CLEAR_QUADS=0` (split), `PVR_G5P_EMPTY_PASS_JOB=1` (GPU job).
- **Arm A is the first run of the draw-less path against Hyprland's own work-buffer memory** (offline produced none).
  If it still shows `clear_only=1 draws=0` passes, suspect the guards first, the dma-buf one above all. A job the
  guards keep prints the same pass line as before; it does not mean the logic is wrong.
- **Follow-up (orchestrator's call):** both default-on paths are reached only by the named gfx-test groups
  `clearq` and `emptyq`, and neither `hypr-gpu.sh regress` nor `integ.sh test` names them. One lane order should
  gain `,clearq,emptyq`.
- **Unproven on hardware [I]:** the clear-quad VS (float compares + selects on `gl_VertexIndex`, vertex push
  constants), and a depth/stencil-only quad (tag write disabled) writing depth/stencil inside a colour pass. Both
  use forms that app draws already use (Qt's colour-mask-0 stencil clips, Zink's vertex-index shaders), but this
  exact program has not run.

### 11.11 Step 1 on the device (perf60h, release8) and cut 3 build record

#### 11.11.1 Step 1 results (orchestrator's run, logs `build/gpu/perf60/s1/`, pass logs `build/release/release8/hypr-adbe-20261103T103558Z` = A, `…T103254Z` = B)

- **Verdict: PASS.** No faults, DISPLAY PASS. Blend ladder 67 rungs PASS (all `ds_*`, max_error 1). `fill_load_small` and
  `fill_load_scissor` exact. The upload trim (`9c40c79bfd1`) stays: `up` = 147–158 kB per pass.
- **Arm A** (perf60h, `PVR_G5P_PASS_LOG=1`): gears 34.05 FPS over 10 s and 37.08 FPS over 60 s. Clean release8 baseline: 33–35.
  Arm C was contaminated (the owner was using the iPad).
- **Arm B** (A + `PVR_G5P_FOLD_CLEAR=1`): gears 34.20 / 37.16 FPS, the same as A.

**Where a frame's CPU time goes [V, steady state = second half of each log, per frame].**
A frame is two jobs: the work-buffer CLEAR pass and the LOAD copy pass.

| Item | ms per frame | What it is |
|---|---|---|
| `pre` (BO_SYNC TO_DEVICE before the ioctl) | 2.6–2.8 | 79.7 MB per LOAD pass (the whole 64 MiB arena chunk + the 12.6 MB target), 104.7 MB per CLEAR pass (chunk + three 12.6 MB images) |
| BUFFER_TO_IMAGE CPU ops, sync in + out | 5.5–6.5 | about 4.4 per frame (SHM client uploads: the software-rendered bar), each syncing 71.3 MB (chunk + 4.2 MB image) both ways, about 0.7 ms each way |
| `post` | 0.15–0.2 | 12.6 MB after CLEAR passes |
| `wait` | 13.4–14.3 | two jobs |

- **Sync throughput** [V]: about 43–49 MB/ms over all passes; 83 MB/ms on clear_only passes.
- **Sync on the CPU, outside `wait`:** 8.3–9.3 ms of a 27–29 ms frame. This is cut 5's target, and it needs both halves:
  - the ICD half (`139fe06c167`) names ranges;
  - the release8 kernel ignores them (whole-BO `BO_SYNC`), which is correct but slow; the kernel half honours them.
- **Expected effect** [I: the measured rate, images synced whole, the arena synced over its used range only]:
  - `pre`: 12.6 MB per LOAD pass and about 38 MB per CLEAR pass, so about 1.1 ms per frame;
  - uploads: about 0.1–0.2 ms each way;
  - in all about 6–7 ms per frame saved.
- **Pass criteria for the next package's arm on release8-mmio:**
  - `pre` bytes about 12.6 MB (LOAD) and about 38 MB (CLEAR);
  - BUFFER_TO_IMAGE in/out ≤ 0.2 ms;
  - `wait` unchanged.
  - Unchanged `pre` bytes = the kernel half is not honouring the range.

**How much of `wait` is sync [I].**
- Only LOAD passes carry a shared dma-buf (the 12.6 MB swapchain buffer; `shared=` 0 on CLEAR passes). Its for_cpu sync at the
  measured rate is ≤ 0.26–0.29 ms per LOAD pass: about 2% of `wait`.
- The rest is fixed per-job cost: an empty clear_only job (0 tiles, no draws) waits 4.1–5.9 ms. A full-panel LOAD with one
  draw waits only about 0.3–1.3 ms more.
- So `wait` is dominated by the number of jobs: kick, TA/3D set-up, firmware, and the kernel's 1–2 ms polling (cut 1).

**Why FOLD_CLEAR left 11 empty jobs, each at a full job's cost [V code + logs].**
- `PVR_G5P_FOLD_CLEAR` acts only inside `clear_split()`: a partial clear, or a clear after draws, in a job with no draws yet.
- The surviving `load=0 clear_only=1 draws=0 tiles=0` jobs are a different shape. They are whole render passes that clear
  the full target and end with no draw: Hyprland's work-buffer clear in a frame where nothing drew into it.
- The pass sequence alternates `C0 d0, L d1, C0 d0, L d1`: the next job samples the cleared image (the copy to the swapchain).
- No clear call comes after a draw, so the fold never sees them. Cut 2's in-pass clear quads would not see them either:
  it is a full clear before any draw.
- `tiles=0` means no geometry. The job still stores its background over all 3072 tiles (`post` 12.6 MB).
- Its cost is the per-job floor. B's total (6507 µs) against A's (4684 µs) is within that floor's spread at n = 11–28.
- **Fix (added to cut 2's scope):** a render job that ends with no draw does not go to the GPU.
  - A colour-only clear becomes the CPU clear op at that point in the op stream (about 0.4–0.9 ms against about 5 ms).
  - A job with no CLEAR at all is dropped.
  - Knob `PVR_G5P_EMPTY_PASS_JOB=1` restores the GPU job.
- Cut 3 also removes them for frames without blur: no work buffer means no clear pass at all.

#### 11.11.2 Cut 3 build record (Hyprland renders straight into the swapchain buffer)

**Toolchain, proven [V].**
- **The device's binary is Omarchy's build:** `hyprland 0.56.2-7` = omarchy-pkgs commit `ebedd694`. Its PKGBUILD's sha256 matches the
  `.BUILDINFO`'s `pkgbuild_sha256sum` (`ed5e44ab…`). It is v0.56.2 + four Omarchy patches:
  - software-renderer;
  - nvidia-egl-teardown;
  - wl-output-global-grace;
  - monitor-rule-vrr.
  Our patch therefore goes on top of those, not on clean v0.56.2. PKGBUILD and patches are vendored in
  `scripts/gpu/hypr-direct/`.
- **Build image `linux-a9-hypr-build:0.56.2-7`** (`scripts/gpu/hypr-direct.sh image`) follows the package's own `.BUILDINFO`
  (300 packages, `scripts/gpu/hypr-direct/pkgs.txt`):
  - 254 exact files from the rootfs build's pacman cache volume (`linux-a9-omarchy-pkgcache`);
  - 11 exact files from the mirror;
  - glaze 9.0.0 and hyprland-protocols 0.7.1 built from their upstream tags;
  - pacman 7.1.0-2 (and its `makepkg.conf`) as in the base image;
  - about 30 nearest-version substitutes where the exact version is gone from every mirror. These are runtime-only or
    header-identical (cmake 4.4.5 for 4.4.4, mesa headers 26.2.5 for 26.2.4, linux-api-headers, pkgconf, …);
  - not installed: nvidia-utils, rclone, wget, python-tqdm (builder extras).
- **Unpatched reproduction (`hypr-direct.sh repro`): bit-identical.**
  - Procedure: `makepkg` of the vendored PKGBUILD in `/src/hyprland`, `SOURCE_DATE_EPOCH` = the package's build date, 2 CPUs.
  - Result: `usr/bin/Hyprland` sha256 `a9e57097798b…`, equal to `/usr/bin/Hyprland`
    on the rootfs and in the cached `hyprland-0.56.2-7` package.

**The patch (`scripts/gpu/hypr-direct/a9-direct.patch`, 5 files, about 150 lines; `src/render/OpenGL.{cpp,hpp}`,
`pass/Pass.{cpp,hpp}`, `ElementRenderer.cpp`).**
- **`begin()`:**
  - If direct render is allowed, bind the output buffer provisionally, with the work buffer's image description so colour
    management targets the same space.
  - Set `mainFB` = `currentFB` = `outFB`.
  - Clear nothing.
  - Otherwise run the stock path (`bindOffloadTarget()` = the original lines, unchanged).
- **Allowed only if all of these hold (`directRenderAllowed`); each refusal is logged on change as `a9-direct: offload work
  buffer: <why>`:**
  - a NORMAL frame to the output's own renderbuffer: not a fake frame, not to-buffer;
  - no screen shader, not crashing;
  - not a mirror, no mirror or screencopy consumer (`needsACopyFB`, `needsUnmodifiedCopy`);
  - no FP16 work buffer;
  - zoom 1 and no zoom animation;
  - the monitor's image description equals the work buffer's: the stock final copy would be the plain primitive copy, no CM.
- **Resolve before the first draw.** `CRenderPass::render()` knows the frame's elements:
  - live blur, precompute blur or a `PreBlur` element → the stock offload path (`resolveDirectRender(true)`);
  - otherwise direct.
  - Any draw before that point (`IElementRenderer::drawElement` while undecided) resolves to offload and keeps a temp FB's binding.
  - A frame that drew nothing resolves to direct: the stock copy of it is empty too.
- **Clears = the stock result exactly.**
  - The stock work buffer is cleared to transparent black, and its damage is copied over the output with blend off.
  - Direct mode therefore clears only the damage no opaque element covers: `simplify()`'s remaining region, kept as
    `m_uncoveredDamage`. Without simplification, the whole damage clipped to the monitor.
  - In a frame with damage and no element at all, the whole damage is cleared.
  - Content under opaque elements is overwritten by them, as `simplify()` already assumes.
- **Buffer age:** the damage is the swapchain buffer's aged damage (`getBufferDamage(bufferAge)`), the same region the stock
  copy writes. So rendering only it into that buffer is correct.
- **Orientation:**
  - `bindFB()` does not change the projection; both targets are `m_pixelSize` in buffer orientation.
  - The stock end copy is 1:1: it undoes the texture transform and nothing else.
  - So elements land identically. To be confirmed by the transform-1 offline case and the device screenshot.
- **`end()`:** a direct frame skips the copy, restores the output FB's description and resets the zoom camera state as stock does.
- **Knob:** `HYPRLAND_A9_DIRECT=0` keeps the stock path in the same binary. `HYPRLAND_A9_DIRECT=2` (test) makes every frame
  take the switch to the offload path at the pass, the path a blur frame takes.

**Build: `hypr-direct.sh direct`.** Applies the patch to the reproduction's tree; same flags and makepkg →
`build/gpu/hyprland-gpu/direct/out/Hyprland-a9-direct`, sha256 **`c226e7e7658b…`**. The reproduction was rebuilt for it and was
bit-identical to the device's binary again (`a9e57097…`). Each decision change
is also printed on stderr as `a9-direct: …`: owner sessions run with `debug:disable_logs`, so Hyprland's own log stops after
the config loads, while stderr goes to `hypr.log` like the ICD's pass lines.

**Offline matrix [V] (`hypr-direct.sh matrix`, `build/gpu/hyprland-gpu/direct/matrix.txt`).**
- Setup:
  - nested on wl-stub over the fake node, 40 s per case;
  - foot and weston-simple-shm as clients;
  - a snapshot of the perf60h stage (`9c40c79bfd1`), `PVR_G5P_PASS_LOG=1`.

| Case | Frames | GPU passes / frame | Refusals | `a9-direct` log |
|---|---|---|---|---|
| stock, base | 2237 | 2.00 (CLEAR work buffer + LOAD copy) | 2 (the known D32 format query) | — |
| **direct, base** | 2271 | **1.00** (LOAD into the swapchain buffer) | 2, same | first frame `offload: zoom` (zoom animation at start), then `rendering into the output buffer` |
| direct, `HYPRLAND_A9_DIRECT=0` | 2245 | 2.00, same as stock | 2 | `offload: disabled` |
| direct, screen shader | 2238 | 2.00, the fallback | 2 | `offload: screen shader` |
| stock, transform 1 | 2243 | 2.00 | 2 | — |
| **direct, transform 1** | 2252 | **1.00** | 2 | direct |
| blur, stock **and** direct | 3 | — (Hyprland dies) | +1: `discard with a depth/stencil test (needs a punch-through pass)` | — |

- **Blur cannot be tested offline.** Both binaries hit the same ICD refusal, so it is a pre-existing ICD limit, not the patch.
  The owner's config has blur off in every section (captured `owner-hypr-config.tar`). The blur → offload resolve is
  covered by code review only, until the ICD draws blur.
- **Offline proves:** the decisions, the passes per frame, the same refusals as stock, no crash.
- **The device proves the pixels:** a scanout screenshot from the direct binary against the stock binary, same state.
  The fake node executes nothing.
- **The device log also answers one open condition:** that the monitor's image description equals the work buffer's there.
  If it does not, every frame logs `offload: colour conversion to the output` and the arm measures stock.

**On the final ICD [V].** Stage `perf60h` = `g5p-perf60-hypr@bc82302f291`, ICD `3d43fbf9…`; 40 s, base config.

| Binary | Frames | Passes / frame | Passes with `clears≥1` |
|---|---|---|---|
| stock | 2249 | 2.00 | 2251 |
| direct | 2248 | **1.00** | 2250 |

- **stock:** the work buffer's damage clears are clear quads in its CLEAR job.
- **direct:** the uncovered-damage clears are clear quads inside the one LOAD job on the swapchain buffer.
- **Both:** 0 splits, 0 CPU `CLEAR_RECTS` ops, the same 2 refusals as before.

**The pass-time switch to offload [V]** (`HYPRLAND_A9_DIRECT=2`, final ICD, `build/gpu/hyprland-gpu/direct/matrix-final2.txt`).
This is the path blur would take, and it cannot run offline otherwise.
- 2259 frames at 2.00 passes per frame.
- Log: `a9-direct: offload work buffer: blur or an early draw`.
- No crash; the same 2 refusals.
- The same binary at default settings: 2234 frames, 1.00 passes per frame.

**Shipping.**
- `bin/Hyprland-a9-direct` goes in the hypr-s2 package.
- The session runs it through a symlink named `Hyprland` (`start-hyprland --path` for owner sessions), so `pgrep -x Hyprland`
  and the watchdog hold.
- `/usr/bin/Hyprland` is never touched.
- Runner plumbing:
  - `hypr-stage2.sh package` with `HYPR_S2_DIRECT_BIN=<file>` adds the binary and writes `hyprland_direct_sha=` into
    MANIFEST.txt;
  - `HYPR_S2_BIN=direct` (`release8-device.sh`: `R8_HYPR_BIN=direct`) writes `HYPR_BIN=direct` into `session.env` and
    `hyprland_bin=direct` into `mode.txt`, and STOPs if the package has no binary;
  - `hypr-s2-session.sh` logs `hyprland_bin=… sha256=…` in `session.log` and START-FAILs on a missing binary;
  - unset, every launch line is byte-identical to before.

#### 11.11.3 DEVICE-READY: one package, arms D and E (release8-mmio kernel, which has cut 5's kernel half)

- **Package:** `build/gpu/hyprland-gpu/perf60h/s2package-direct-c226e7e7/hypr-s2-a9.tar.gz`, sha256
  **`f9a2f31eefd3…`**.
  - MANIFEST: `mesa=g5p-perf60-hypr@bc82302f291`, icd `3d43fbf9…`, `hyprland_direct_sha=c226e7e7…`.
  - **Package directories are never rewritten once flown.**
    - `perf60h/s2package` (`ad349a4c…`) is an earlier build of this package. It must not be flown.
    - `perf60h/s2package-752721c7` is §11.10's package rebuilt byte-identically: same ICD, no `bin/`. The pin-ladder runs
      use it.
  - Contents: cuts 2, 4, 5 (ICD half, page-aligned ranges), the draw-less passes, and `bin/Hyprland-a9-direct`.

**Arm D** (cuts 2+4+5, stock Hyprland):
`R8_HYPR_PK=build/gpu/hyprland-gpu/perf60h/s2package-direct-c226e7e7 R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1" scripts/release/release8-device.sh hypr`

D passes when all of these hold:
- no fault, recovery or bad job; DISPLAY PASS;
- `perf60-passt.py <run>/hypr.log`:
  - `clear_only` passes only into dma-buf memory (`shared=12.6 MB`), a few per 77 frames as in §11.12;
  - the other draw-less passes show up as `cpuop kind=8`, not as jobs;
  - no `render pass split` line;
- on a kernel with `render_user_event_wake 2000` and `render_user_sync_range 3`:
  - `pre` about 0.24 ms per LOAD pass and about 0.7 ms per CLEAR pass. The bytes the ICD names are already 17.9 / 51.5 MB
    (§11.12); the time falls only if the kernel half honours the ranges;
  - BUFFER_TO_IMAGE in and out ≤ 0.2 ms (was about 0.7 at 6.3 MB);
- gears above 55.0 FPS (§11.12's wake2000 baseline, sync range off), toward the 60 Hz cap.
- [I] about 7 ms per frame back from sync (§11.12).

**Arm E** (D + Hyprland direct):
`R8_HYPR_PK=build/gpu/hyprland-gpu/perf60h/s2package-direct-c226e7e7 R8_HYPR_BIN=direct R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1" scripts/release/release8-device.sh hypr`
**Superseded by §11.13:** `c226e7e7` crashed in the owner session (Omarchy's titlebars plugin, ABI). Arm E flies
`s2package-direct-dd2baac6`.

E passes when all of these hold:
- `session.log` shows `hyprland_bin=/tmp/hypr-s2/hyprbin/Hyprland sha256=c226e7e7…`; `mode.txt` shows `hyprland_bin=direct` (the
  release freeze refuses such a run);
- `hypr.log` shows `a9-direct: rendering into the output buffer` after start-up;
- per frame, one 1536x2048 LOAD job on the swapchain buffer and no work-buffer CLEAR job. Passes per frame about half of D's;
- the scanout screenshots (`scanout-*.png`) match D's at the same state: content, orientation, no stale regions after
  workspace switches and window moves;
- no fault; gears ≥ D.

If E fails:
- `a9-direct: offload work buffer: colour conversion to the output`: the iPad's monitor description differs from the work
  buffer's, and E measured stock. That is a finding, not a failure of the patch.
- Wrong pixels: re-run E with `R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1 HYPRLAND_A9_DIRECT=0"`. It must look like D.

#### 11.11.4 Clean-up, gates added, and what stays

- **`hypr-gpu.sh regress` now also runs `vk10,cts1,clearq,emptyq`** (orchestrator's decision). The new ICD must pass it.
  It is compared with the old ICD only when the old one has the same scenes. A pre-cut-2 ICD ignores the unknown groups,
  so that order is new-only.
- **The fake node enforces the kernel's ioctl checks** (orchestrator's decision; `patches/mesa-a9/test/a9-fake-node.c`, inventory
  `build/gpu/fakenode-test/REPORT.md`).
  - Every check the release8-mmio kernel (`8ae02dbbb9`) makes on user input, with its errno and order, cited to file:line.
    That includes BO_SYNC's whole-16-KiB-page range rule (`drm-vm.inc:275-283`, `drm-validate.h:31-35`).
  - Refusals log `A9FAKE REFUSE`.
  - Test `patches/mesa-a9/test/test-fake-node-kernel-rules.c`: 184/184 on the new fake, 110 failures on the old one,
    including accepting `139fe06c167`'s unaligned BO_SYNC.
  - The current ICD against it:
    - offline Hyprland: 4568 submits, 0 refused;
    - blend and qs ladders PASS (119 rungs, `refused=0`).
  - Not covered: g5p-gfx-test's in-ICD mock transport never forms kernel requests, so it cannot catch this class. Fixing it
    is a separate Mesa change.
- **First run** (old `/tmp/perf60h-base` = `9c40c79bfd1`, new `3d43fbf9…`):
  - 270/270 compiles identical;
  - 4588 scene files identical in the four old orders;
  - `vk10,cts1,clearq,emptyq`: new 48 PASS, 0 FAIL (old 46, no clearq/emptyq scenes);
  - `result=PASS`.

- **Stays:** the image `linux-a9-hypr-build:0.56.2-7`, the `$D/dl` downloads, the vendored PKGBUILD and the patch.
  Rebuilding the binary after a patch change is `hypr-direct.sh direct`, about 2 minutes incremental.
- **Remove when cut 3 is settled:** the build volume `linux-a9-hypr-direct-src` (`hypr-direct.sh clean`); everything with
  `hypr-direct.sh purge`.

### 11.12 Cut 1 landed: the remaining cuts re-ranked against 55 FPS (2026-11-03)

**The new baseline [V].** Source: `build/gpu/perf60/s3/run-b.txt`, `measure-wake0.txt`, `measure-wake2000.txt`.
- **Set-up:** release8-mmio (`8ae02dbbb9`) + memclk; Hyprland owner session on package `752721c7…` (cuts 2, 4, 5-ICD and the
  draw-less passes; run `build/release/release8-mmio/hypr-adbe-20261103T110019Z`).
- **Result:** `render_user_event_wake` 0 → 2000 took gears from **39.2 to 55.0 FPS**, 25.5 → 18.2 ms per frame. Cut 1 was
  worth about 7.3 ms per frame, about 3.6 ms per job at two jobs per frame.
- **So the per-job fixed wait (§11.11.1: 4.1–5.9 ms for an empty job) was mostly the kernel's polling.** What is left in
  `wait` is about 2.4 ms per job [I: 6.0 ms measured before the wake, minus 3.6].

**What that run's pass log shows about cut 5 [V].** Kernel `render_user_sync_range=0`, i.e. the ICD half alone:

| Item | Bytes the ICD names: before (arm A) → now | Time per item: before → now |
|---|---|---|
| `pre`, LOAD pass | 79.7 → **17.9 MB** | 964 → **945 µs** |
| `pre`, CLEAR pass | 104.7 → **51.5 MB** | 1374 → **1346 µs** |
| BUFFER_TO_IMAGE, each way | 71.3 → **6.3 MB** | about 700 → **714 / 697 µs** |

- **The bytes fell and the time did not:** the kernel still syncs whole BOs. So all of this time is cut 5's kernel half, and
  it comes back only with `render_user_sync_range` on.
- **This is a clean prediction for the sync-range measure:**
  - [I, at the 75–83 MB/ms the narrow syncs show] `pre` about 0.24 ms (LOAD) and 0.7 ms (CLEAR);
  - each upload about 0.09 ms each way.
- **Cut 2 on the device [V]:**
  - no `render pass split`;
  - 3 `clear_only` jobs left in about 77 frames, all into the 12.6 MB dma-buf (`shared=12.6 MB`), which the guard keeps on the
    GPU by design;
  - 8 CPU `CLEAR_RECTS` ops: the draw-less passes now executed as CPU clears.

**Per frame at 55 FPS (18.2 ms), what is left [I from the pass log above, wait scaled by the measured wake gain].**

| Item | ms / frame now | After the fix | Cut |
|---|---|---|---|
| Upload sync (4.4 BUFFER_TO_IMAGE per frame, whole-BO in the kernel) | **about 6.2** | about 0.8 | **5, kernel half** |
| `pre` sync (two passes) | about 2.3 | about 0.9 | **5, kernel half** |
| Work-buffer CLEAR job (its wait, `pre`, `post`, build) | about 4.2 (about 3.5 after cut 5) | 0 | **3, direct** |
| Remaining GPU + fixed wait of the copy/LOAD job | about 2.4 | about 2.4 | 7 (TA fixed cost) |
| Everything else (Hyprland CPU, gears, the rest of the submit path) | about 3 | — | 6 (async submit overlaps it) |

**Ranking now.**
1. **Cut 5's kernel half (`render_user_sync_range=3`) with the ICD half already flying:** about 7 ms per frame. It is
   mostly the uploads of the software-rendered shell (SHM → BUFFER_TO_IMAGE), which pay a 64 MiB arena sync each way.
   On its own it brings the frame to about 11 ms, i.e. the 60 Hz cap [I].
2. **Cut 3 (Hyprland direct, arm E):** about 3.5–4 ms per frame. It drops the whole work-buffer job, so one job per frame.
   With cut 5 it is the margin that keeps 60 FPS under heavier damage, and it halves the GPU jobs, which matters for the
   multi-app goal.
3. **Cut 6 (async submit):** about 2.4 ms of `wait` per remaining job could overlap Hyprland's CPU work. It is worth more
   once 1 + 5 + 3 are in, because the frame is then mostly that wait.
4. **Cut 7 (TA fixed cost):** what remains of the 2.4 ms per job after the wake; to be measured from the `fin/td/ta`
   medians of a wake2000 run.
5. **Cut 4 (upload trim): landed** (`up` about 148 kB per job). **Cut 2: landed.** Its remaining device question is the
   dma-buf-kept clear_only jobs (3 per 77 frames), which are too few to rank.

**Next device steps, in order:**
- **The sync-range measure, already queued by the orchestrator (`render_user_sync_range=3`, `run-c`).** Pass if:
  - `pre` falls to about 0.24 / 0.7 ms per LOAD / CLEAR pass;
  - BUFFER_TO_IMAGE falls to ≤ 0.2 ms each way;
  - gears reaches about 60.
- **Arm E (cut 3)** on the sync-range kernel, from a new package directory (§11.11.3, path in the build report).

### 11.13 Arms D and E on the device; E's crash was plugin ABI, fixed (2026-11-03)

**D: PASS, at the 60 Hz cap [V]** (orchestrator's run).
- Set-up: release8-mmio2, pin 100, `event_wake 2000` + `sync_range 3`, package `s2package-direct-c226e7e7`, stock Hyprland; log
  `build/gpu/perf60/sDE/run4.txt`, run `build/release/release8-mmio2/hypr-adbe-20261103T115937Z`.
- Gears **59.43 / 59.55 FPS**. DISPLAY PASS 41/41, 0 faults.

| Pass | `total` | `pre` (bytes) | `wait` |
|---|---|---|---|
| CLEAR full | 5320 µs | 570 µs (35.4 MB) | 4358 µs |
| LOAD partial | 4817 µs | 240 µs (17.9 MB) | 4485 µs |

- Uploads about 0.05 ms each way at 5.0 MB; `clear_only` n = 3.
- All of §11.11.3's cut 5 criteria are met.

**E (`c226e7e7`): the patched binary ran, then Hyprland came up on its recovery config [V].**
Run: `…T120338Z`, scanout `build/gpu/perf60/sDE/shot-E.png`.
- What ran:
  - `hyprland_bin=direct`, sha `c226e7e7…`;
  - `a9-direct: rendering into the output buffer`;
  - no colour-conversion offload.
- The first instance rendered about 80 frames, one job per frame. Then it died silently (`debug:disable_logs`).
- `start-hyprland` restarts a Hyprland that exits uncleanly with `--safe-mode`: the yellow `recoverycfg.lua` banner, no shell.

**Root cause [V offline].**
- Omarchy's `default/hypr/workspace-modes.lua` loads `/usr/lib/omarchy-hyprland-titlebars/titlebars.so` while any window
  floats. That plugin is built against the stock `hyprland-0.56.2-7` headers (its `.BUILDINFO`).
- `c226e7e7`'s patch added data members to `CHyprOpenGLImpl`, and one to `CRenderPass`. The renderer embeds the pass
  (`m_renderPass`), so every renderer field after it moved.
- **Reproduced offline:** `conf/plugin.lua` (every window floats, the plugin loaded, bars on), crash report in the run
  directory.
  - `#4 titlebars.so COmarchyFloatingBarPassElement::boundingBox()` ← `#5 Render::CRenderPass::simplify()`;
  - a SIGSEGV right after the first floating window maps, before any GPU refusal.

**Fix (`a9-direct.patch`).**
- **The binary keeps the stock ABI.**
  - No header gains a data member: `Pass.hpp` is untouched, and `OpenGL.hpp` gains only non-virtual member function
    declarations, which change neither layout nor vtable.
  - The state lives in file-local statics: `s_a9` in `OpenGL.cpp`, `s_uncoveredDamage` in `Pass.cpp`. There is one
    render thread.
- **Stencil parity.**
  - The work buffers carry the monitor's shared depth/stencil texture (`CMonitorResources::initFB`).
  - A direct frame attaches that same texture to the output buffer, and detaches it at the end of the frame or on the
    switch to offload. Stencil users (plugins drawing on the main FB) therefore see what they see in stock.
  - Hyprland itself uses the stencil only for blur, which is offload anyway.

**Proof [V].** Binary `dd2baac6c83d…`. The reproduction was rebuilt for it: bit-identical
to the device again.

- **Plugin, bars on every window, the plugin's pass element reached:**
  - `c226e7e7`: SIGSEGV in the plugin;
  - `dd2baac6`: gets past `simplify()` and dies exactly as **stock** does: the ICD refuses the bar draw (`discard with a
    depth/stencil test (needs a punch-through pass)`), then GPU-reset abort.
  - This is an ICD gap, the next item.
- **Final ICD (`3d43fbf9…`), 40 s each** (`build/gpu/hyprland-gpu/direct/matrix-abi.txt`):

| Case | Frames | Passes / frame | Refusals | Crash |
|---|---|---|---|---|
| dd2baac6, plugin loaded, every window floating, bars on an unused tag (as on the device) | 2239 | **1.00** | 2 | none |
| stock, the same | 2242 | 2.00 | 2 | none |
| dd2baac6, base | 2228 | 1.00 | 2 | none |
| dd2baac6, `HYPRLAND_A9_DIRECT=2` | 2244 | 2.00 | 2 | none |

**Package and arm E.**
- Package `build/gpu/hyprland-gpu/perf60h/s2package-direct-dd2baac6/hypr-s2-a9.tar.gz`, sha256
  **`935069cbafc0…`** (icd `3d43fbf9…`, `hyprland_direct_sha=dd2baac6…`).
- **Arm E:**
  `R8_HYPR_PK=build/gpu/hyprland-gpu/perf60h/s2package-direct-dd2baac6 R8_HYPR_BIN=direct R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1" scripts/release/release8-device.sh hypr`
- **Pass, against D:**
  - one Hyprland instance for the whole run: no second `Creating the ConfigManager!` in `hypr.log`, no recovery banner;
  - the quickshell bar present in the scanout, matching D's shot;
  - `a9-direct: rendering into the output buffer`;
  - one 1536x2048 job per frame;
  - gears 60;
  - E's value is GPU headroom: compare the per-frame job count and `total` with D. D pays about 10 ms of jobs per frame
    (CLEAR 5.3 + LOAD 4.8); E should pay about one job's worth.

**Next: the punch-through gap** (orchestrator, 2026-11-03).
- The ICD refuses a draw that discards in its fragment program while depth or stencil is tested or written.
- This blocks Hyprland blur, Omarchy's titlebars on workspaces where they draw, and probably other apps.
- Plan: Apple's encoding (HSR pass type, ISP state, the discard/depth-stencil interaction), `ds_*`-style blend-ladder rungs,
  and offline Hyprland with blur and titlebars on every window. The offline configs that die on stock today become a gate.

### 11.14 Discard with depth/stencil (punch-through)

Offline lane, 2026-11-03. Mesa `g5p-punch-ds@8150a8195df` on `g5p-perf60-hypr@bc82302f291` (worktree
`build/third_party/mesa-a9-punchds-src`, its own meson tree; lane `HYPR_LANE=punchds`, outputs
`build/gpu/hyprland-gpu/punchds`). Nothing ran on the device. [V] = read from a capture, a decompile or a compile by
Apple's own toolchain; [I] = inferred.

#### 11.14.1 Apple's encoding

Sources: the gles3b capture (`build/gpu/ios-capture-bundle/20261101T175626Z`, scene `g3b-discard`, decoded in
control-flow.md §6.2), AGXMetalA9's `getShaderPassInfo`/`setFragmentVariant` (labwc114-passtype-tile-read.md §1,
decompiles in `build/gpu/labwc114/re/`), and new offline compiles with Apple's A9 backend:
`tools/mesa-a9-punchds/compile.sh` (one metal-tt run per attachment variant; metal-tt merges and reorders identical
programs within one run, and rejects unknown pipeline keys, so the depth keys are really applied) and
`tools/mesa-a9-punchds/apple-passtype.py` (RESULT PASS, 18 programs; it imports the labwc114 port of the two
functions, `build/gpu/punchds/apple/apple-passtype.json`).

ISP state of a discarding object that tests or writes depth/stencil:
- **Pass type** [V]: FAST_PUNCH_THROUGH (4), or PUNCH_THROUGH (2) when a written channel reads the destination
  (`A & B`). The depth/stencil state does not enter `getShaderPassInfo`. A blending program with colour write mask 0
  (GL's `glColorMask` under `GL_BLEND`) has neither A nor B, so it is FAST_PUNCH_THROUGH (probe `ds-none-blend`).
- **ISPA/ISPB** [V]: Apple's discard under D32F Less + write is (captured state words omitted):
  the opaque draw's block (`00120f00`) with ISPA bits 24..26 = 4, front and back; ISPCTL and ISPB unchanged.
  `setFragmentVariant` clears and ORs only the pass type (front `& f8ffffff`, back `& f8efffff`), so every depth and
  stencil field, `dwritedisable` included, keeps what the depth/stencil state put there. Stencil under a discard was
  not captured; that it follows the same rule is [V] for the code path (the OR) and [I] for the capture.
- **Tag write** [V]: `getShaderPassInfo` sets `tagwritedisable` only for kill mode 0 (`B == 0`). A discarding program
  that writes no colour keeps the tag write with output mask 0: Apple's ISPCTL for it is upass 0, tag write on.
- **What is deferred** [I]: nothing in the words marks a deferred write; the ISP's punch-through pass does it (PowerVR
  model: depth/stencil pass ops and the depth write of a punch-through object wait for the shader's feedback; fail and
  depth-fail ops are known before shading). That is why Apple's capture can keep `dwritedisable` 0 with write on.

Shader side:
- **The feedback instruction** [V for the bytes, I for the name]: Apple's discarding programs contain nothing but the
  discard token besides the ordinary code: `04 68` (unconditional), `04 60` (predicate set by the test before it),
  `04 61 SS 00` (register condition). `f_discard` with a no-colour target is 24 bytes: iterator, test, `04 60`, end
  `00 80`. There is no separate ATST/alpha-feedback op (Rogue's `ALPHAF`/`DEPTHF` + `ATST`). So the token is the
  feedback: [I] from that and from hardware, where cf7 (`04 61` in FAST_PUNCH_THROUGH, no depth) passed 210/210 frames
  (control-flow.md §6.2; Rogue's ISP waits for punch-through feedback, and cf7 did not hang).
- **Depth/stencil does not change the program** [V]: `f_discard` and `f_discard2` compile to identical bytes with no
  depth, D32F and D32F_S8 attachments (MTLDepthStencilState is not part of the pipeline at all). Kill mode 1 in all.
- **One token** [V]: `f_discard2` (two conditions) gets one `04 60`; the second test folds into the predicate.
  Ours emits one `04 61` per condition. Whether a second token in a punch-through pass sends a second feedback (and
  the first one already released the depth write) is unknown, so under a depth/stencil test the ICD now runs Apple's
  shape (below).
- **Blending** [V]: `f_discard` under premultiplied blending keeps `04 61` before the epilogue (186 B), kill mode 1,
  PUNCH_THROUGH. Our compiler turns such discards into a colour select (discards_to_select(), Henrik's), which is
  exact without a depth/stencil write but lets a discarded fragment write depth/stencil.
- **Kill mode and feedback** [V/I]: the kill mode comes from `__GPU_METADATA` (1 = discard); it selects the pass type
  and the `kill` flag that the caller (`0x207d28be0`) uses next to the PDS state; the triangle-merge-disable bit of
  every discarding program (control-flow.md §6.2) is already set by the ICD. Placement: Apple's token comes before the
  colour stores, as ours (`fs_discards()` at `DISCARD_AT`).

#### 11.14.2 What changed (commits on `g5p-punch-ds`, `Generated-by: LLM`)

| commit | what |
|---|---|
| `562a1298caa` | pco/g5p: key `one_discard` (renamed `punch` in `99fdc84b2b1`): every top-level discard becomes one `demote_if` on the OR of the conditions (the flag form cf7 already runs); the program reports its token count and whether its discards became a select |
| `47e48416d0f` | g5p: the pipeline compiles that variant (`fs_punch`) for a program with more than one token; it must keep the program's interface, else there is none |
| `0a7ad579228` | g5p: the refusal goes. `isp_words_ds()` already emitted Apple's words; a kill program keeps its tag write with no colour, and a blending kill program with colour mask 0 runs FAST_PUNCH_THROUGH; several tokens under a test take the variant |
| `d714a2106a9` | g5p-gfx-test: group `punchds` |
| `99fdc84b2b1` | g5p: the punch form keeps a blending program's token (no select); taken under a depth/stencil **write** when the program's discards were a select (Omarchy's titlebars); pass type, tag write and the merge-disable bit follow the program actually placed |
| `8150a8195df` | g5p-gfx-test: the blend scenes |

Every other program and draw keeps its bytes: the variant exists only beside programs with several tokens or a
select discard, and is placed only for the draws that need it. Still refused by name: rasterizer discard with a
depth/stencil attachment; a draw that needs the punch form when the variant could not be built (different
interface); everything refused before for other reasons (partial write masks, MSAA, general blend + discard).
The colour-only path (no depth/stencil attachment) keeps its old tag-write rule for a no-colour discard (an
invisible draw; Apple would shade it).

#### 11.14.3 Offline proof

- **gfx-test group `punchds`** (`HYPR_LANE=punchds hypr-gpu.sh punchscenes`, PASS, 9 scenes), each one job, the ISP
  block found word for word in `ppp.bin`:
  `pd-depth` (D32F Less + write) = Apple's g3b-discard block exactly; `pd-depth-test` `04320f00` (dwritedisable);
  `pd-stencil` (D32F_S8, ALWAYS ref 1 REPLACE) (bytes omitted) ×2; `pd-stencil-none` (colour mask 0,
  blending on) (bytes omitted) ×2 (output mask 0, tag write on, FAST_PUNCH_THROUGH); `pd-faces` (back
  ref 2 INCR_CLAMP) (captured state words omitted); `pd-discard2` (two conditions) Apple's block,
  and its code has one `04 61 rr 00` against two for the same pipeline without the test (`pd-discard2-off`);
  `pd-blend` (premultiplied + discard, Less + write) (bytes omitted) ×2 with the token kept (1 against
  0 for `pd-blend-test`, the select under the test alone, still TRANSLUCENT `01320f00`). The depth group's
  `depth-discard` check (refused before) now expects the draw to record; it is not submitted, so it adds no file.
- **regress** against the same commit's own build (`HYPR_REGRESS_OLD=build/gpu/hyprland-gpu/punchds/base`, the
  base ICD from this tree, b5351c0a): **270/270 compiles identical; 4588 scene files identical in 4 orders; gfx-test
  0 failures in every order incl. `vk10,cts1,clearq,emptyq` (48 PASS); result=PASS** (`punchds/regress-vs-base/`).
  Against es3's da5034b6 (the default) the compiles are 270/270 identical and the scene diff is the perf60 base's own
  (clear quads etc., predates this lane; perf60h gated against its predecessor the same way, §11.4): **result=FAIL
  there, inherited** (`punchds/regress-es3.log`; new ≡ base on every scene file, so the 19 differing scenes differ
  identically for `bc82302f291`).
- **Build tree:** the lane's meson tree was removed after packaging (disk); `HYPR_LANE=punchds hypr-gpu.sh configure`
  then `build` regenerates it (~1 h at -j2).
- **tramp** `761dbd4a…`; **stage** ICD `3db34f4c145a…`; **offline** (es3 stage vs this): 2812 / 2811 frames, refusals
  5 / 2 (the 2 = D32_SFLOAT queries), 0 link failures; **qsladder** PASS; **blendladder** PASS, 83 rungs OFFLINE, 0
  refusals, the 10 new ones included.
- **Hyprland, 40 s each** (`hypr-offline.sh`, `HYPR_BIN=dev`, `foot weston-simple-shm`, `PVR_G5P_PASS_LOG=1`):

| case | frames | passes/frame | refusals | crash lines |
|---|---|---|---|---|
| blur.lua, stock (`perf60h` stage) | 3 | 2.33 | 3 (+ `discard with a depth/stencil test`) | 1 |
| blur.lua, punchds | **2177** | 2.01 | **2** | 0 |
| plugin.lua (titlebars), stock | 3 | 2.33 | 3 (the same) | 1 |
| plugin.lua (titlebars), punchds | **2180** | 2.00 | **2** | 0 |

  Traced runs (`pd-blur-trace`, `pd-plugin-trace`, first 40 jobs; `build/gpu/hyprland-gpu/offline/pd-traces.tar.zst`) show what Hyprland draws: the blur stencil mask
  (bytes omitted) ×2 (colour mask 0, scissor, FAST_PUNCH_THROUGH, ALWAYS→REPLACE 1) and the titlebar's
  (bytes omitted) ×2 (colour + premultiplied blend, PUNCH_THROUGH, NOTEQUAL→REPLACE 1, the punch form).
  The first plugin run of the intermediate build refused that bar draw by name (the select under a stencil write),
  which is why `99fdc84b2b1` exists.

#### 11.14.4 DEVICE-READY (orchestrator)

Package `build/gpu/hyprland-gpu/punchds/s2package-punchds-8150a81/hypr-s2-a9.tar.gz`, sha256
**`0a058ac802c4…`** (ICD `3db34f4c…`, tramp `761dbd4a…`,
`mesa=g5p-punch-ds@8150a8195df`, `bin/blend-ladder` `3e0e8eb7…` with the rungs below). Kernel: release8 as running.

1. **Ladder first** (one process per rung, warm-safe; unpack beside, never over the running `/tmp/hypr-s2`):
   *(Device/host command block omitted; it targets the private workspace.)*
   Pull `/tmp/qs/blend-ladder-<UTC>/`. PASS means every rung prints `PASS` (within 1 LSB; the blend rungs may show f16
   rounding, judged as in blend-general.md), no `unsupported/fault` / `RENDER-V3 lost` / timeout in dmesg. Reading a
   failure: `ds_discard_depth` wrong = the pass type or the token's polarity; only `*_write_order` wrong (CLR missing
   where discarded) = a discarded fragment still wrote depth, the deferral premise fails; only
   `ds_discard2_depth_write_order` wrong = the merged token; a hang (`terminal kind=timeout`) on `ds_discard_stencil`
   = a no-colour punch object without feedback (tag write / output mask 0); only the `blend` rungs wrong = PUNCH_THROUGH
   with a kept token (Henrik's A10 tile loss was the TRANSLUCENT pass; this is Apple's pass, never run on A9, and the
   titlebars depend on it); only `ds_discard_stencil_faces` wrong with CLR and CLR2 swapped = the recorder's
   front/back word swap for a CCW front face (Rogue's rule, first A9 test), not punch-through.
2. **Hyprland with blur and titlebars** (only after a clean ladder): the session on this package,
   `R8_HYPR_PK=build/gpu/hyprland-gpu/punchds/s2package-punchds-8150a81 R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1" scripts/release/release8-device.sh hypr`,
   then turn blur on in the running session, with the session's socket as `s2-tap.py` finds it:
   `scripts/omarchy/ssh.sh 'sudo -n -u linux env XDG_RUNTIME_DIR=/run/user/1000 HYPRLAND_INSTANCE_SIGNATURE=$(basename $(ls -d /run/user/1000/hypr/* | tail -1)) hyprctl keyword decoration:blur:enabled true'`
   [I: the keyword path of the 0.56.2 Lua build is not tested here; else set `decoration.blur.enabled` in the owner's
   config and restart] and open foot. PASS: Hyprland alive the whole run, no recovery banner, 0 `G5P refuse` beyond
   the D32_SFLOAT pair in `hypr.log`, no GPU events, the blur visible behind foot in the scanout, gears unchanged.
   Titlebars: the same with Omarchy's plugin (the owner's own setup) on a workspace where the bars draw.

### 11.15 es3-baseline scene differences: verdicts

Offline (2026-11-03). Question: every Hyprland ICD of the s1fix → perf60h lineage fails `regress` against es3's ICD
(`da5034b6`, `g5p-es3@6550721a684`) on "19 default-order scenes", with 270/270 compiles identical. Which output is
right? **Answer: the lineage's, everywhere. Nothing is wrong, so there is no fix branch and no package.**

**The list was cut off.** `regress` printed the differing scenes through `head -20`: a blank first line plus 19 names.
The real difference against es3 is **92 scenes in the default order**, 87 / 51 / 16 in the other three orders. The
gate now prints the whole list.

**Method.** Each binary set's `g5p-gfx-test` ran in the container in the 4 orders, with the scene trees kept
(`build/gpu/es3fix/scenes/`). Then `scripts/gpu/regress-golden/golden.py classify` compared each scene word for word.

- Job dirs are paired best-first. Their names are mkstemp's, and their mtime and even birth-time order tie or flip:
  a first pairing by mtime produced false "LOAD vs clear" diffs in `depth-load`.
- A difference counts as VA-only when every differing json field or file word equals one of that job's BO VA
  deltas, scaled by a power of two, as 32 bits or as half of a 64-bit value. Job counts, file sizes and every
  non-VA json field must be equal.
- Bisect points: the lanes already built (`b2f05e4c0a1`, `b80ccd064a9`, `0a4cdcd8541`, `bc82302f291`). Plus
  incremental builds of 3 targets at `ccae6f6ae8e`, `284e2f6ba84`, `aa76b79299c` and `3215220866d` in s1fix's
  configured tree.
  - `9c6b97a3be7` and `3f09d7dce38` do not build in that tree: its `build.ninja` lists `pco_g5p_general.c`, which
    they don't have yet.
  - Intermediate objects can be stale in such a tree. The attribution rests on the endpoints matching byte for
    byte, not on each step being pristine.

**Result, the same in all 4 orders:**

- **4 semantic scenes**, the ISP words of the lineage's two pass-type fixes.
- **Everything else is VA-only** (88 / 83 / 47 / 12 scenes), all from `284e2f6ba84`.
  - `ccae6f6ae8e` (its parent) is byte-identical to es3 in every scene.
  - `284e2f6ba84`'s own build is byte-identical to `bc82302f291` in every scene except the 4 ISP ones.
  - `3215220866d` is byte-identical to `bc82302f291` in every default scene. No perf60 cut (clear quads, draw-less
    passes, sync ranges, skip-empty-tiles, twiddle knob) changes a scene of these orders: the gfx-test pins the old
    path in the old groups, and the new paths have their own groups (`clearq`, `emptyq`, `skip-empty-tiles`).
- **Why the VAs move.** `284e2f6ba84` gives allocations ≥ 4 MiB their own BO, with VAs from a `util_vma_heap` that
  takes freed ranges back. es3 used a bump pointer that only grew.
  - All scenes run on one device, so every scene after the first freed large image (`load-area-desktop`, a
    1536×2048 RGBA8 target) has its BOs lower. The deltas are −31358976, then −43941888 (= −31358976 −
    12582912, one more 1536×2048×4 image).
  - Where a BO lands is not a correctness question.

| scene(s) | changed fields (es3 → lineage) | introducing commit | verdict | evidence | action |
|---|---|---|---|---|---|
| `depth-bias` `depth-clear-attachments` `depth-load` `depth-s8` `depth-stencil` `depth-store` `depth16-load` | job.json `color.va`, `color.pbe[1]` (address bits), `depth.zls[1..2]`, `resources[].va`, `app_bos[].va`; 2–5 `state.bin` words (texture/ZLS addresses) | `284e2f6ba84` | layout-only | [V] every word explained by the BO deltas; `ccae6f6ae8e` ≡ es3, `284e2f6ba84` ≡ `bc82302f291` byte for byte | none |
| `dontcare-area` `es3-zs-d32` `es3-zs-d32-tex` `es3-zs-d32s8` `es3-zs-d32s8-stencil` `es3-zs-d32s8-tex` | the same fields (`zls` where a ZLS plane exists); 3–6 `state.bin` words | `284e2f6ba84` | layout-only | [V] as above. ZLSCTL (`zls[0]`, e.g. es3.md §2.3's `0xe2004`) is unchanged; only ZSTORE/stencil/texture VAs move | none |
| `g3t-dyn-ubo` `g3t-rt-bgra8-srgb` `g3t-rt-rgb10a2` `g3t-rt-rgba8-srgb` `g3t-samp-aniso` `g3t-samp-mirror` | `color.va`, `color.pbe[1]`, `resources/app_bos` VAs; 2–4 `state.bin` words (texture state address) | `284e2f6ba84` | layout-only | [V] as above. PBE/texture format, swizzle and sampler words unchanged | none |
| the other 69 VA-only default scenes (`g3t-tex-*`, `g3t-samp-repeat/zero`, `g3t-swizzle`, `load-area-desktop`, `load-then-clear`, `mrt2*`, `mrt4*`, `tt-*`, `vy-*`) and the VA-only scenes of the other orders (incl. `cts1-*`, `vk10-immutable`) | VAs only | `284e2f6ba84` | layout-only | [V] as above | none |
| `hypr-premult` `rounded-border` | ppp.bin front ISPA `003e0f00→013e0f00`, back ISPA `00100f00→01100f00`: passtype OPAQUE→TRANSLUCENT | `3f09d7dce38` | lineage | [V] Apple's `getShaderPassInfo` gives a destination-reading program TRANSLUCENT, `f_blend_premult` ISPA `013e0f00` (labwc114-passtype-tile-read.md §1). The Mesa117 trampoline patched exactly these words on hardware for labwc (ibid. §4). Device: OPAQUE fails qs11 `load_blend*` with stale tiles, TRANSLUCENT exact on qs12 (hyprland-gpu.md §10). Range bisect: absent at `284e2f6ba84`, present at `aa76b79299c`; `3f09d7dce38` is the only pass-type commit in between, and its recorded gate lists these scenes and words (§10) | gate records the lineage words |
| `hypr-straight` | the same two words | `3f09d7dce38` | lineage | [V] as above; straight-over reads the destination (A&B rule); blend-ladder 59/59 on device (hyprland-gpu.md §11.7) | gate records the lineage words |
| `hypr-mask0` | ppp.bin ISPCTL `03c40000→00240000`: upass 15→0, tagwritedisable 0→1 (bpres kept) | `3215220866d` | lineage | [V] encoding: Apple `f_mask_none` has no written channels and tag write disabled (getShaderPassInfo port, labwc114 §1: ISPCTL = outMask<<22 \| tagwd<<21). Build bisect: `aa76b79299c`→`3215220866d` changes only this scene. Device-proven in a D24S8 target (blend-ladder `ds_clip_premult`, §11.7); colour-only mask 0 is [I] on device | gate records the lineage words; optional rung below |

**es3 was wrong, compensated.** On these 4 scenes raw es3 records OPAQUE / tag write on. labwc on the iPad is right
only because the Mesa117 trampoline rewrites blend passes to TRANSLUCENT (labwc114 §4). Hyprland and quickshell use
the raw ICD, which is why the lineage fixed it in the ICD.

**Device rung (optional, not blocking).** One blend-ladder case covers colour-only mask 0. Pass 1 draws the
pattern. Pass 2, on the same colour-only target with LOAD, draws a full-screen colour-write-mask-0 quad, then a
premultiplied quad over half the screen. PASS = the pattern is exact where only the mask-0 quad drew (it hides
nothing), and the blend is ≤ 1 LSB elsewhere. Wrong pixels in the mask-0 region would mean the tag write or upass
is wrong on hardware. (Not added: `tools/mesa-a9-hyprland-gpu/blend-ladder.c` belongs to the qtpass lane; the
orchestrator decides.)

**The gate (`scripts/gpu/regress-golden/`, used by `hypr-gpu.sh regress`).**

- `golden-<order>.txt`: es3's own output for the 4 orders. `make-golden.sh` regenerates it from es3's binaries and
  gate inputs alone; an independent rerun at another container path reproduced all 4 files byte for byte.
- `verdicts.txt`: the 4 lineage scenes, each with its commit, a one-line reason, and the exact words it must show
  against es3 (`expect`). The `intentional` kind is for a later lane's deliberate change; none so far.
- `golden.py check`, per order, against es3's run in the same regress (es3's binaries run as a third side when
  `HYPR_REGRESS_OLD` is another baseline):
  - es3's run must equal the golden (stale golden → FAIL).
  - A scene passes if it equals the golden, or differs from it VA-only (verdict es3), or shows exactly the
    recorded words (verdict lineage).
  - A lineage scene back at es3's bytes fails.
  - Scenes es3 has no counterpart for are listed as ungated.
  - `golden.py selftest` flips one bit in a copy of a VA-only scene and must see a semantic difference.
- Unchanged: the predecessor comparison (still all 4 orders, same bytes) and the `vk10,cts1,clearq,emptyq` order
  (new ICD passes, compared with the old ICD only when it has the scenes; not in the golden, since es3 has none).
- `HYPR_REGRESS_DIR` writes the record elsewhere, used to gate another lane's build without touching its record.
- Checked offline before wiring it in: `ccae6f6ae8e` (pre-fix) fails the golden on exactly the 4 lineage scenes;
  `bc82302f291` passes.

**Runs of the new regress** (records in `build/gpu/es3fix/regress-*.out`; the scene evidence is in
`build/gpu/es3fix/scenes-evidence.tar.zst`). Every run: 270/270 compiles identical, the selftest SEMANTIC, golden
PASS in all 4 orders. Per order: 40/38/37/39 equal, 88/83/47/12 VA-only, 4 verified lineage fixes, 0 mismatches.

| new | predecessor (`HYPR_REGRESS_OLD`) | predecessor | golden | result |
|---|---|---|---|---|
| perf60h `bc82302f291` | es3 (default) | 246 scenes differ (92/87/51/16, now listed in full) | PASS | FAIL, by design: byte identity with es3 cannot hold after `284e2f6ba84` |
| perf60h | s1fix `0a4cdcd8541` | 4588 files identical in 4 orders | PASS | **PASS** |
| punchds `8150a8195df` (not a fix lane: the other built lane, record in `build/gpu/es3fix/regress-punchds*`) | es3 (default) | 246 scenes differ | PASS | FAIL (same reason) |
| punchds | perf60h | 4588 files identical; `vk10,cts1,clearq,emptyq` compared with the old ICD | PASS | **PASS** |

A lineage lane is gated against its own predecessor and, now, against es3's verified output in the same run. With
the default old side (es3) only the golden half can pass.

### 11.16 E on r2, and the missing-bar dump: age guard, debug lines, bar-check arm (2026-11-03)

**E passed on r2 [V]** (orchestrator's run). Run `build/release/release8-r2/hypr-adbe-20261103T134450Z`, summary
`build/gpu/perf60/E2/run.txt`.
- One `ConfigManager`, no recovery, DISPLAY PASS.
- Gears 59.55 / 59.98 FPS.
- One 1536x2048 LOAD job per frame (n = 7107, `total` 5700 µs, `wait` 4999 µs), 0 faults.

**One intermittent defect [V].** `build/omarchy/barpatch/before.png` (about 14:47, 7 s after foot opened) has no bar.
- The wallpaper shows at x ≥ 1470: pixel (1500,30) = (138,50,127), not the bar's (93,36,88).
- `hyprctl layers` still lists the bar as mapped.
- Every other dump of that session has the bar.

**What the code and the run rule out.**
- **Aquamarine's swapchain never measures buffer age** [V]. `CSwapchain::next()` sets `*age = options.length` ("we always just
  rotate"), and the damage ring repaints the last N frames' damage. That is right only if every `next()` is followed by
  exactly one ring rotation and a render into that buffer.
- **Stock relies on it exactly as much as direct** [V]: its end copy also writes only the damage. So by reading alone, direct
  rendering does not change whether the age is right.
- **The r2 log has one decision change** ("zoom" at start-up, then direct) **and no offload ↔ direct switch afterwards** [V].
  A stale buffer from a mode switch is ruled out.
- **Candidates left:**
  1. an age miss on the device: a flip that fails or is rolled back, or a `next()` without a render;
  2. the bar's element missing, or discarded by `simplify()` in that frame;
  3. the bar's SHM texture uploaded transparent (BUFFER_TO_IMAGE with cut 5's range syncs). This one would be the ICD's,
     and stock would share it.

**Change (`a9-direct.patch`; binary `82c727070593…`).**
- **Buffer-age guard** in `IHyprRenderer::beginRender`, covering every NORMAL frame, offload and direct alike.
  - Per monitor, each swapchain buffer is recorded with the damage-ring rotation it was last drawn at. These are weak
    pointers, so a buffer freed by a swapchain reconfigure never matches a new one at the same address.
  - If Aquamarine's age disagrees with that count, or the buffer was never drawn here, the whole output is repainted
    (`getBufferDamage(0)`).
  - From the second use of a buffer on, a mismatch also prints `a9-direct: buffer age doubt (swapchain age A, drawn E
    rotations ago): full repaint` on stderr, at most 32 times.
  - The guard only ever enlarges damage.
- **`HYPRLAND_A9_DIRECT_DEBUG=1`** prints on stderr:
  - per frame, `a9dbg frame … buf= age= expect= doubt=` and `a9dbg damage own= use=`;
  - per pass, `a9dbg pass mode= direct= damage= uncovered= els=N: name[!]@box …`: every element, with `!` = discarded.
- **ABI:** still no data member in any header; the state is file-static in `Renderer.cpp` and `Pass.cpp`.

**Offline [V]** (final ICD `3d43fbf9…`, 50 s each, `build/gpu/hyprland-gpu/direct/matrix-age.txt`).
- **Map/unmap cycle** (`conf/mapcycle.lua`): 40 foot windows open and close, about 1.4 s each, while weston-simple-shm stays
  mapped.
  - `scripts/gpu/hypr-direct/age-check.py` checks, per buffer, that every frame repaints the union of the frames' own
    damage since that buffer was last drawn.
  - **2862 frames, 3 buffers, 0 violations.** 3 doubts: each buffer's first use, whose content is undefined.
  - No `buffer age doubt` line: Aquamarine's age always matched the real rotation.
  - 2856 frames direct; 47 offload passes are the window-open snapshots (FULL_FAKE).
- **The same binary elsewhere:**
  - base: 1.00 passes / frame;
  - the plugin loaded with bars on an unused tag: 1.00;
  - `HYPRLAND_A9_DIRECT=2`: 2.00;
  - only the 2 known refusals, no crash.
- **The defect does not reproduce offline,** where the fake node has no real flips. It is either device-side (ADBE flips:
  a failed or rolled-back commit) or not damage at all (the bar's buffer or its upload). The device arm below tells them
  apart.

**Package:** `build/gpu/hyprland-gpu/perf60h/s2package-direct-82c72707/hypr-s2-a9.tar.gz`, sha256
**`1e4534351b34…`** (icd `3d43fbf9…`, `hyprland_direct_sha=82c72707…`).

**Device arm: bar check (E + debug), then the same against stock as a control.**
1. **E with the debug lines:**
   `R8_HYPR_PK=build/gpu/hyprland-gpu/perf60h/s2package-direct-82c72707 R8_HYPR_BIN=direct R8_EXTRA_ENV="PVR_G5P_PASS_LOG=1 HYPRLAND_A9_DIRECT_DEBUG=1" scripts/release/release8-device.sh hypr`,
   then `scripts/gpu/hypr-direct-bar.sh 20`. The script:
   - takes a reference dump `ref.png`, which must show the bar;
   - runs 20 foot open/close cycles via `hyprctl dispatch` and `pkill -n foot`, with a scanout dump 2 s after each step:
     40 dumps;
   - checks each dump's bar strip (x 1475..1530, full height) against the reference. The bar is translucent, so the
     reference is a dump: the missing-bar dump matches only 7% of the bar dump's strip;
   - pulls `hypr.log.zst` and dmesg.
2. **Control: the same with stock Hyprland** (no `R8_HYPR_BIN`, the same package and env), then `hypr-direct-bar.sh 20` again.

**PASS:**
- `BAR RESULT PASS` in every E dump;
- `python3 scripts/gpu/hypr-direct/age-check.py <out>/hypr.log.zst` gives `RESULT PASS`, with no `buffer age doubt` line in
  the log;
- 0 faults.

**If a dump misses the bar, read the frame that produced it in `a9dbg`:**
- `doubt=1` with a printed `buffer age doubt`: an age miss. The guard repaints the whole output on the next use of that
  buffer, but the missed frame itself was already wrong, so find which flip or `next()` broke the rotation.
- The bar's surface element absent or `!` in that frame's `a9dbg pass`: an element problem, not an age problem.
- The element drawn and its region in `use`: the bar's texture, i.e. an upload or sync issue. Check the BUFFER_TO_IMAGE
  `cpuop` lines next to it. If the stock control also loses the bar, it is not the direct path.
- **Volume:** the debug lines add about 25 kB/s to `/tmp/hypr-s2/run/hypr.log` (device RAM), about 1.5 MB a minute. Keep
  the session to the arm.

### 11.17 Missing bar under direct render: not damage, not Hyprland's element logic; device matrix (2026-11-03)

**Device result [V]** (orchestrator, `build/gpu/perf60/bar-chain-20261103T201112Z`, package `s2package-direct-82c72707`).
- **Direct:** BAR FAIL in `open-03 … open-20`. Each of those dumps matches only 7% of the reference bar strip; every close
  dump, and `open-01`/`02`, match 100%.
  - age-check PASS: 230 frames, 0 violations, 4 doubts (first uses).
  - 0 faults, no ICD refusals beyond the 5 known D32 queries.
- **Stock control:** BAR PASS, 40/40 dumps at 100%.

**What the dumps show [V]** (`open-05`, direct vs stock, side by side).
- In direct, **three things are missing: the bar, foot's blue active border and its inner glow.**
- The wallpaper, foot's surface, the titlebars plugin's bar and the dock are all drawn.
- Stock has all of them.

**The element stream is the same; the job is not the cause of the missing pixels [V].**
- **Foot open, from `a9dbg pass`, 11 elements:** clear, wallpaper, foot's group (shadow, plugin titlebar, foot surface,
  border, inner glow), bar `@735,0,33x1024`, dock, a top layer `@270,0,498x1024`, cursor.
  - The bar is never discarded where its strip is damaged.
  - The uncovered region is empty (the wallpaper is opaque).
- **Damage and age are sound.**
  - Each foot open gets three full repaints, one per swapchain buffer: two 10× full-damage frames, then an exact full one.
  - Later frames damage only `x < 1470`, which is correct: the bar did not change.
  - age-check PASS.
- **The ICD jobs carry the same draws as stock's work-buffer jobs** (`G5P pass` histograms):
  - 18-, 46- and 64-draw jobs in the same counts, the same clear-quad counts;
  - `skip_flag=0` everywhere;
  - no refusal.
- **What remains different:**
  - **The target.** Direct jobs render into the 1536x2048 **BGRA8 dma-buf scanout image** (format 44). Stock jobs render
    into an **RGBA8 work buffer** (format 37). Both are linear (the ICD refuses twiddled render targets) and both are
    CLEAR-loaded for full-damage frames.
  - **Partial-damage frames.** Direct runs LOAD passes on the scanout image with in-pass clear quads (`L, 46 draws, 4
    clears`); stock runs CLEAR passes on the work buffer with the same 4 quads.
- **Ruled out:**
  - the stencil attachment: offline traces show `depth.present=false` in every job, stock and direct alike;
  - window snapshots nested in a frame: they are made from event handlers (`Window.cpp:2587` on close), not inside a frame;
  - blend state: Hyprland always uses `glBlendFunc(ONE, ONE_MINUS_SRC_ALPHA)`, and only blur and the stencil-rounding paths
    touch the colour mask;
  - a GL scissor or blend leak across frames;
  - the titlebars plugin's stencil path: its stencil-tested draw is exactly what the ICD refuses, and the device logs show
    no such refusal.

**Reading [I].**
- The three missing elements look like draws whose source alpha came out as 0: their output equals the destination
  (plain wallpaper under the bar, an invisible border).
- The border's shader discards outside the ring and blends, so it runs PUNCH_THROUGH. The glow and possibly the bar's
  layer (if it has a rounding or alpha rule) do the same. Foot's surface and the dock are plain TRANSLUCENT.
- So the leading hypothesis is a **destination-reading (general blend epilogue) or punch-through draw that misbehaves on
  the BGRA dma-buf target**, or those draws' uniform data arriving wrong in the direct job. In the offline traces the
  arena layout of a direct job is shifted (`ppp`/`vdm` offsets +0x80…0x100, more `user.bin` data than stock's), so a
  positional diff cannot tell. A per-draw decoder is missing.
- **Which of these it is cannot be settled offline: the fake node executes nothing.**

**Device matrix** (`scripts/gpu/hypr-direct-bar-matrix.sh`, same package, no rebuild, one owner session per variant,
`rollback-labwc` between). Command:
`scripts/gpu/hypr-direct-bar-matrix.sh build/gpu/hyprland-gpu/perf60h/s2package-direct-82c72707 10`

| Variant | Env (plus `PVR_G5P_PASS_LOG=1 HYPRLAND_A9_DIRECT_DEBUG=1`) | PASS means |
|---|---|---|
| `stock` | /usr/bin/Hyprland | control (expected PASS) |
| `offload2` | direct binary, `HYPRLAND_A9_DIRECT=2` (stock path at every pass) | expected PASS: the defect needs the scanout target |
| `direct` | direct binary | expected FAIL (reproduces the defect in this session) |
| `blendgen0` | `PVR_G5P_BLEND_GENERAL=0` | the general blend epilogue on the scanout target is the cause |
| `quads0` | `PVR_G5P_CLEAR_QUADS=0` | in-pass clear quads on a LOAD pass are the cause |

- **If neither `blendgen0` nor `quads0` fixes it:** next is an ICD rung (blend-ladder style) that draws, into a BGRA8
  dma-buf target, a premultiplied discarding quad (PUNCH_THROUGH) and a premultiplied texture over a pattern, against an
  RGBA8 target. Then flip the kernel's `render_user_sync_range` off for one run, to exclude cut 5's range syncs.
- **E stays opt-in** (`R8_HYPR_BIN=direct`) until the matrix pins the stage and it is fixed.

### 11.18 Bar loss: matrix v1 and the scanout ladder rule out the GPU target; matrix v2 knobs (2026-11-03)

**Matrix v1 [V]** (`build/gpu/perf60/bar-matrix-20261103T213943Z/matrix.txt`, 10 cycles each).

| Variant | BAR |
|---|---|
| stock | PASS |
| offload2 | PASS |
| direct | FAIL 10/10 |
| blendgen0 | FAIL 9/10 |
| quads0 | FAIL 10/10 |

- Age-check PASS in every arm; 0 faults.

**Scanout ladder v2 [V]** (`build/gpu/perf60/scanout2-20261103T215140Z`, after fixing the import to Hyprland's attributes).
- Result: `default=PASS blendgen0=PASS sync0=PASS`.
- All 12 rungs, xrgb/argb/abgr × tex/punch/stack/stack_load, are exact on the adbe dumb BO: through `glReadPixels` and through
  the BO's own mapping.
- So the GPU draws Hyprland-like streams into the scanout format, the dma-buf, LOAD stacks and punch-through correctly.
- The loss is specific to Hyprland-direct's real frames on its swapchain.
- v1's first import failure was the harness's: no modifier attribute, and an `eglQueryString` that reset the error.

**Also ruled out [V].**
- The CPU ops are the same in both arms (uploads, and 5 vs 8 `CLEAR_RECTS` on a 12.6 MB image).
- Aquamarine scans out Hyprland's own dumb BOs: no multi-GPU blit.

**Matrix v2.**
- Binary `Hyprland-a9-direct` `6420733ee326…`. The reproduction was bit-identical to the
  device's again.
- Test knobs, default off, each logged on stderr when set:

| Knob | Variant | PASS means |
|---|---|---|
| `HYPRLAND_A9_DIRECT_FULL=1` | `full` | damage or buffer age |
| `HYPRLAND_A9_SWAPCHAIN=2/4` (stock 3) | `sc2` / `sc4` | sc4 PASS with sc2 worse = rendering into a buffer the display still scans out |
| `HYPRLAND_A9_DIRECT_FINISH=1` (`glFinish` before the commit) | `finish` | the render fence signals before the GPU is done |
| `HYPRLAND_A9_DIRECT_STENCIL=0` | `nostencil` | the stencil-parity attachment |
| `HYPRLAND_A9_DIRECT_SPLIT=1` (`glFlush` after every element: one GPU job per element) | `split` | an interaction between draws inside one job |

- **Offline [V], map/unmap config, 40 s:**
  - no knobs: 1.02 passes / frame, 3 buffers, age-check PASS;
  - all knobs on: each knob logged, 2 buffers, 2215/2215 frames repainted in full, 8.54 passes / frame, age-check PASS, the
    same 2 refusals, no crash.
- **Package:** `build/gpu/hyprland-gpu/perf60h/s2package-matrix2-6420733e`, sha256 `2a7056df32ac…`.
- **Run:** `scripts/gpu/hypr-direct-bar-matrix.sh build/gpu/hyprland-gpu/perf60h/s2package-matrix2-6420733e 10 build/gpu/perf60/bar-matrix2-<UTC> direct full split finish nostencil sc4 sc2 offload2`

### 11.19 Missing bar, matrix v3: exact damage and same-BO LOAD (2026-11-04)

**Device evidence [V, supplied by orchestrator]:**
`build/gpu/perf60/bar-matrix2-20261103T233812Z/matrix.txt`: direct FAIL 9/10, full PASS,
split FAIL 5/10, finish and nostencil FAIL 9/10, sc4 FAIL 3/10, sc2 FAIL 9/10, offload2 PASS.
Zero faults; the old age audit passed. This supersedes §11.17's claim that damage was ruled out:
that audit checked only extents and cannot detect an interior hole. Swapchain-length sensitivity does
not prove scanout overlap. Full repaint passing is consistent with either history or preservation.

**Discriminating rung [implemented, hardware pending]:** same Hyprland binary, ordinary direct versus
`HYPRLAND_A9_DIRECT_LOAD=1` (`load` in `hypr-direct-bar-matrix.sh`). In the LOAD arm, only direct-frame
colour clears become unblended, unrounded overwrite draws on the currently bound output attachment.
The draw emits the original raw RGBA (no premultiply/second colour conversion), scissors each requested
rectangle, and restores blend state. The clear element keeps stock's empty-region convention (full clear). No copy, target switch, flush,
extra job, driver environment change, or forced full damage is added. Fallback/offload frames retain
stock clears. This is a Hyprland patch, independent of the ICD or kernel driver name. It is diagnostic,
default-off, and is not yet a validated production fix.

`a9dbg frame` adds a buffer index; buffer pointer and rotation remain the durable identities. `a9rect`
logs **all** half-open rectangles for `own`, `acquired`, `pass`, uncovered regions and each drawn element.
`bar` and `pixels` report intersection with physical x=1470..1536 (override with `HYPRLAND_A9_BAR_X0/X1`).
`a9target` identifies the GL draw framebuffer/output object and the LOAD arm. Per-frame age and expected
age remain logged. `rect-check.py` subtracts actual region unions instead of comparing extents and
prints each frame's index, BO, age, bar overlap and missing accumulated damage. The matrix saves this
table in `<variant>/frames.txt`. An unchanged bar **should** be omitted from damage when its BO
already contains it: bar=0 alone is not a damage bug. Only missing required historical damage is one.

**Interpretation [I]:** if LOAD passes with the same damage and normal direct fails, preservation/clear
semantics are implicated. Confirm offline job logs show LOAD (no colour clear) before drawing that
conclusion. If exact historical damage is absent from acquired or pass regions, fix that bookkeeping
instead. If both fail with exact damage coverage and actual LOAD, neither diagnosis is established;
do not promote a full-repaint workaround. The scanout ladder's exact LOAD result remains relevant.

The rectangle auditor's synthetic proof includes a hole whose bounding box is full: the old audit
accepts it, the exact audit identifies the missing 2x2 square. This proves the checker distinction,
not hardware preservation. Live correctness and speed require the orchestrator's v3 result.

**Offline verification [V, 2026-11-04]:** raw logs are in
`build/gpu/hyprland-gpu/offline/bar3-{direct,load}/`. Direct: 889 audited frames, 0 violations;
LOAD: 887 frames, 0 violations. Both emit 1.03 passes/frame, 0 crash lines, only the two known D32
image-format queries. The LOAD run's three repeatedly used swapchain target VAs each LOAD every job
(296/296/295 uses, 887 total); 27 snapshot/other jobs at the same resolution retain stock clears.
`load-check.py` explicitly distinguishes those targets from snapshot work buffers. These are command
encoding and region proofs; the fake node executes no pixels and its frame rates are not device FPS.

The first raw-region audit incorrectly used `getBufferDamage(1)`, which itself collapses >8 rectangles
to an extent. That created false holes in subsequent history comparisons. The sealed binary instead logs
`CDamageRing::m_current` inside `getBufferDamage(1)` **before** simplification; `own-summary` is separate.
The auditor counts raw `own` once per frame even when debug reporting asks for age 1 again.

**DEVICE-READY:** `build/gpu/hyprland-gpu/perf60h/s2package-bar3-aad95213/DEVICE-READY.md`.
Archive sha256 `c7801b2cdac0…`;
Hyprland `aad952133d9b…`.
ICD is byte-identical to matrix2 (`3d43fbf96504…`).
Run `scripts/gpu/hypr-direct-bar-matrix.sh build/gpu/hyprland-gpu/perf60h/s2package-bar3-aad95213 10 build/gpu/perf60/bar-matrix3-<UTC> direct load`.
No device accessed; all workspace changes left uncommitted. Production fix remains conditional on the
matrix3 evidence; the bounded-overwrite implementation is available default-off for that rung.

### 11.20 Matrix v3: ×10 is stock forced-full damage, not a scale conversion (2026-11-04)

**Device [V]:** `build/gpu/perf60/bar-matrix3-20261104T171639Z/`: direct and LOAD both
lose the bar in all 10 open screenshots, no exact-region violations, no faults (151/153 audited frames).
That excludes a missing historical damage region and wrong CLEAR-vs-LOAD selection as sufficient explanations.
It does **not** prove the GPU's LOAD implementation preserves an unchanged bar correctly.

**Where ×10 originates [V code]:** unpatched Hyprland 0.56.2 `IHyprRenderer::renderMonitor()` assigns
`damage = {0, 0, transformedWidth * 10, transformedHeight * 10}` for forced-full frames, disabled/monitor
damage tracking or damage-blink cleanup. This runs after `beginRender()` (and after the acquired-damage log).
It is the stock deliberately oversized full-region sentinel, not fixed point and not a second monitor scale.
`CRenderPass::simplify()` intersects it with `{0,0,pMonitor->m_transformedSize}` *before* deriving element damage.

**Passing controls disprove ×10 alone [V captures]:** matrix2's `full/hypr.log.zst` has 25 direct ×10
frames; `offload2/hypr.log.zst` has 28 ×10 frames, yet both controls pass. Direct has 25 such frames.
Matrix3 direct frame 85 shows the oversized pass, then every dispatched element (including the
`CSurfacePassElement@735,0,33x1024` bar, border and glow) has `a9rect ... rects=0,0,1536,2048`.
In its 11-element direct passes, the bar is dispatched 30 times and culled 14; in LOAD, 32 dispatched and 16
culled. Culling on later left-only damage is expected. Dispatch metadata cannot prove actual GL clipping
or shader execution, hence a draw-time state audit rather than another extent-based inference.

**Existing scanout ladder limit [V code]:** `tools/mesa-a9-hyprland-gpu/blend-ladder.c:sc_stream()`
`SC_STACK_LOAD` draws the wallpaper, ends the pass, LOADs, and then draws the window, border **and bar**.
It proves rendering the bar after LOAD, not retaining a previously drawn bar through subsequent partial
frames that omit the bar. Thus the old claim that this ladder ruled out every preservation defect was too broad.

**v4 source changes [V code, hardware effect pending]:** direct passes normalize the sentinel to the output
pixel bounds before processing; normal partial damage stays partial and is not expanded. No offload copy or
full repaint is introduced. This bounds correction enforces the direct-pass domain but is **not a proven fix
for the missing pixels**: simplify already bounded element damage, and both passing controls had ×10 frames.
With `HYPRLAND_A9_DIRECT_DEBUG=1`, actual `glDrawArrays` calls log element name, framebuffer, program, scissor
box/enabled, viewport, RGBA write mask and stencil enable (`a9gl`). `gl-check.py` joins those to the pass element
metadata, including the bar bbox, and saves `gl-state.txt` in each device matrix arm. No class layout changes.
The matrix's screenshot scratch files now use `/var/tmp`; session logs already resolve through the release8
stage symlink to `/var/tmp/a9-stage/hypr-s2/run`, rather than tmpfs.

**Offline [V]:** `build/gpu/hyprland-gpu/offline/bar4-{direct,full}/`.
Direct: 840 exact-audit frames, zero region violations; 3,043 border/glow draws, zero wrong-target or fully
masked draws. Full: 787 frames, zero region violations; 7,390 such draws, zero wrong-target or fully masked.
Both 1.04 GPU passes per stub frame, no crash, two known D32-format queries. These establish encoded
regions/state, not pixel correctness, absence of shader/LOAD defects or device FPS.

**DEVICE-READY, candidate + diagnostic, not a production-fix claim:**
`build/gpu/hyprland-gpu/perf60h/s2package-bar4-682b9b68/DEVICE-READY.md`.
Hyprland SHA256 `682b9b686f47…`;
archive SHA256 `c16b39a31d0f…`.
The ICD remains `3d43fbf96504…`.
Run the usual matrix with this package and arms `direct full`; no reboot/kernel change. If it still fails
with the bar's actual GL draws using the right target and valid clips, move below dispatch/scissor to a
retained-bar partial-frame fixture or a shader/job trace; do not claim a Hyprland pixel fix from normalization.
No device accessed; workspace changes uncommitted. Build uses the owner's `-j(12/N)` policy and available-memory
floor (the v4 build logged N=1, -j12, 22,979,208 KiB available).
