# GPU status (updated 2026-11-06 evening)

Read this first. It is the current state of the A9 GPU work: what works, what doesn't, and what is
being worked on. Details live in the kernel branch and `docs/gpu/`.

## Night update (2026-11-06, 22:20): bug1 fixed, R35 sealed and guard-clean, ~1,196 CTS cases fixed

**Bug1 (image-store tail loss): FIXED, proven on hardware.**
- **Cause:** the merged Mesa CDM tail had dropped iOS's end-of-pass barrier DMA task.
- **Proof:** r3c/r3d/r3e rungs exact. Trigger: workgroup width < 32.
- **Commit:** 75d9fa4d72a (Apple target words, default on, `PVR_G5P_CDM_END_BARRIER=0` opt-out).
- **Doc:** `night-known-bugs-20261106.md` (not published).
- **Publication:** a byte-identical encoder form `f8def07d608` exists for the a9-main port; the provenance review is pending.

**R35 = R33-held + that fix, without texmerge.**
- Sealed as fbefd215a57 (archive `8e8f523b…`).
- Device guards g3 + g2 both 1000/1000, 0 new failures, no faults.
- R35 is the head after iOS. Its compute proofs (r4 A/B, bar100 42-sequence, history (g)) fly first after iOS.

**CDM stop: separate root cause, fix built.** L3 (`L3-cdm-late-write-teardown.md` (not published)):
- **Cause:** the kernel frees a context's VM before PBE/TEXAS write-back drains, because compute finish lacks the full flush.
- **Fix:** kernel `a9/gpu-compute-cdm-flush@89beb53435` does a job-end flush. Its same-boot on/off proof is `DEVICE-READY-cdm-flush.md` (not published).
- **NIGHTSET:** stays safe until that proof passes.

**Topic arms proven on hardware tonight**, 0 new failures each, under their probe/env:

| Topic | Cases fixed |
|---|---|
| L10 XFB idtail | 166 |
| L9 texstate | 24 |
| L9 shadow | 510 |
| L9 operands | 46 |
| L10 shared-var | 9 |
| L10 unit-z | 10 |
| L7 derivatives | 26 |
| L11 MRT blend | 35 |
| L7 vtx-CF (ALU part only) | 42 |
| L7 integer builtins | 328 |

- **Also measured:** L11 subword is +100 Pass, plus 116 newly exercised Skip→Fail, with 0 Pass→Fail.
- **Not promoted:** XFB SERIAL (30 regressions).
- **R36 candidate** (R35 + L9 texstate/shadow/operands + L10 idtail) is at 14d75cb56e9, gates running, seal held.

**Projection, excluding optional:**
- GLES2 96.86%; 96.98% with proven topics.
- GLES3 90.92%; 92.82% with proven topics.
- Ledger: `cts-proven-topic-projection-20261106.md` (not published).

**Desktop:** the labwc119 desk camp was deleted in the afternoon build/ cleanup and can't be re-staged, so the owner's p2 desktop is down until the Orchard migration. Native packets now use the session-safe helper `NATIVE-SAFE-r1-20261106.md` (not published).

**iOS witness:** min / r16b / r8 captured, and they drove the shadow, R16 and subword fixes. witness-ms (82 scenes) is sealed for the next iOS window.

## Current state (2026-11-06 evening)

This block is the authoritative summary. The sections after it are a dated log, newest first. Their older "open" or
"building" notes are superseded where this block says otherwise. The full recap with evidence paths is
`recap-20261106.md` (not published). The ranked plan for after the Orchard migration is
`paths-forward-20261106.md` (not published).

**Tomorrow the iPad moves to Orchard (omarchy-a).** Our GPU kernel comes back as a custom BLS entry
(`orchard launch --entry`), with our Mesa on omarchy-a's userspace. Release9d warm kexec, the desk-bench restore and
the `/var/tmp` stages go away.

**Mesa rounds** (branch `g5p-1b-release9-next`; receipts `build/gpu/release9-mesa/rounds/roundNN/ROUND.json`; docs
`release9-roundNN.md`):
- **R13–R32 are sealed.**
  - R13 `bd8c596746e`, R14 `6954164a5df`, R15 `9bfba40ad2e`, R16 `2238a7e3c31`, R17 `e2f31edf4e7`, R18 `c775f8c9cb8`.
  - R19 `64457182c3a`, R20 `0100e9bb814`, R21 `2989852e35f`, R22 `7bf8026180c`, R23 `cb499d37704`, R24 `22f3cb1d8ef`.
  - R25 `559fde96f0b`, R26 `35fca747f9f`, R27 `23d6ea61bd3`, R28 `e5ba4e8af28`, R29 `a2b7922abbe`, R30 `fe5c6835f65`.
  - R31 `80b40f40500`.
- **Current head: R32 `a3de5c91fb7`** (empty dispatch + native occlusion queries).
  - Archive SHA256 `69fc836b436b…`.
  - Sealed 2026-11-06 11:52 UTC.
- **R33 `a17890daf30` is prepared, not sealed.** It is R32 plus the image-store integer-coordinate form `9ac2541f2d1`.
  Host gates PASS (archive `6381361a…`); it is held for the bug1-imgload device proof (`release9-round33.md`).

**Kernel.**
- release9d `07653c41992` (`build/release/release9d-speed07653c4199`).
- **Query workloads need queryocl `7bfc904d3894`**, one commit on 07653
  (uname `7.3.0-rc1-release9d-g7bfc904d3894`, branch `a9/gpu-compute-query-ocl`). On plain 07653 a query-carrying
  render job is rejected whole, and Mesa reports DeviceLost.
- Docs: `DEVICE-READY-kernel-queryocl.md`, `release9-round32.md`.

**Conformance** (2026-11-06 projection: `scripts/gpu/cts-projection.py`, stored output
`cts-projection-20261106.txt` (not published). It takes the newest retest round per packet over the r9 full-run base:
GLES2 fix-g2-02/03/r15/r23; GLES3 fail-a-r23, fail-b-r18, fail-c-r18, unrun-a-r10, unrun-b-r23):

| Suite | Pass | Cases | Rate | Note |
|---|---|---|---|---|
| GLES2 | 16,495 | 17,165 | 96.1 % | |
| GLES3 | 39,675 | 44,727 | 88.7 % | hazard shard 78 excluded |
| GLES3.1 | not run | 37,802 | — | packets ready; tonight's run planned (q79) |

- **R31 guards PASS** on GLES2 and GLES3 (`build/gpu/cts-gles{2,3}-r9-guard/rounds/*-r31/`).
- **GLES3 skip retest on R31:** 1,390 cases → 78 Pass, 168 Fail (96 named refusals, 72 wrong results), 1,144 Skip,
  zero crash/hang. 730 of the skips are rejections of formats ES3 requires (`cts-gles3-skips-r31-triage.md`).
- **GLES3.1 has never run past its canary.**
  - The first canary failed on `load_num_workgroups`. The canary1 fix replaces it with a renderer query
    (`DEVICE-READY-gles31-r31-safe.md`, `cts-canary1-harness-compat.md`).
  - Tonight: 19 canary1 normal partitions on R32 + queryocl, after both guards (`DEVICE-READY-gles31-r32.md`).
  - The 12 query-negative cases are a separate packet (`DEVICE-READY-gles31-query-r32.md`).

**The four compute hang/crash bugs:**
1. **imageLoad: the hang is gone.** Native imgstore/imgload are exact and retire. Zink still reads 384/4096 stale
   words; the fix `9ac2541f2d1` is packeted and waits for the device (`DEVICE-READY-bug1-imgload.md`).
2. **Barriers: exact R31 already passes** bar64/65/100/128 (`DEVICE-READY-speed-barrier-r31.md`). Stability3, on the
   `1743790a45b` stack, saw one bar100 timeout. The sequence1 stress (14 × bar100) is pending tonight
   (`DEVICE-READY-speed-barrier-sequence1-queryocl.md`).
3. **Empty dispatch: FIXED.** r2 22/22, 0 faults; in R32 (`DEVICE-READY-compute-empty-r31.md`).
4. **compSwap: R31 PASS** in dEQP's shapes. The shared and image forms stay named refusals
   (`DEVICE-READY-gles31-cas.md`).

**Occlusion queries: FIXED on hardware.** r4: three cases, copied=cpu=1152, nine jobs retired. Needs the queryocl
kernel (`DEVICE-READY-query-native-r4.md`).

**Vertex textures (R21)** (`desktop-gl-vertex-textures.md`, `R21-*.md`):
- **On by default:** 2D, array, 3D and cube, plus offsets.
- **On hardware:**
  - R16: 283 of 578 fixed;
  - R20 cube: 119 of 295;
  - R22 offsets: 28 of 69;
  - R24 gradients: 8 of 42. Its 119 control "failures" came from the old exclusive selector, and R30's additive
    selectors fix that (`R21-additive-selectors.md`).
- **Not flown yet:** the R31 gradient (472 cases) and VS shadow (438) packets.
- **Integrated in sealed R29 behind explicit selectors, focused CTS not yet run:** size-LOD and uniform TBO.

**The A10 developer's GLES2 branch** (`g9p-gles2-a10@c44de203bcc`, 27 commits):
- mapped against R32 (`a10-gles2-port-map.md`, open items in `a10-gles2-port-open.md`);
- one port so far, texture triangle-merge `ac4ef0befa2`: DEVICE-READY, pixels pending (`a10-gles2-port-texture-merge.md`).

**build/ cleanup incident (2026-11-06).**
- **What broke:** the host cleanup deleted gate inputs (the WSI runtime, the step 6/7 oracles, the corpus270
  baseline) and the desktop camp `labwc119`.
- **Repair:**
  - the oracles were re-recorded from sealed R31, and corpus270 was restored verbatim from R31;
  - a full R32 recheck passed with a byte-identical archive (`69fc836b…`);
  - all 40 canary1 CTS archives verify.
- **Docs:** `release9-gate-cleanup-repair.md`, `step-oracles-rerecorded.md`, `corpus270-restored.md`,
  `cts-cleanup-audit-20261106.md`.
- The p2 desktop no longer comes up, and it won't be rebuilt before Orchard.

**Compute and perf, last measured** (the speed lane is paused, `speed-lane-paused-20261106.md`):
- **FMA:** 104.7 GFLOP/s (`g5p-1b-compute-fma@ab73c2b7ae6`).
- **Bandwidth:** 8–8.8 GB/s at 64 MiB, about 45 % of the 19.2 GB/s LPDDR4-2400 peak.
- **Desktop:** combined-bench2c, where labwc on the GPU beats pixman on drag, scroll and glmark2 and uses less RAM;
  only idle misses the bar.
- **R16_UNORM (r11-stages1):** uploads exact, clears and draws wrong, R32 formats exact. That isolates the
  narrow-format clear/EOT path (`DEVICE-READY-r11-stages1.md`).

**Largest open GLES3 families** (counts from the newest round per packet; the details and owners are in the recap):
- XFB high vertex inputs: 369.
- texture.shadow: 432. Needs an iOS capture.
- shaders.loops 166, fragment_out.array 144, texture.units 100. These come from fail-c on R18, and R27/R30 may have
  moved the first two, so retest them.
- MSAA renderbuffers: 120. Needs a capture and an owner decision.
- Required-format skips: 730.

## Works on hardware

- **2026-11-06 ~12:12: compSwap PASS on exact R31.** ssbo-32, ssbo-321, ssbo-444 and ticket are exact, with 0 cmpxchg
  mismatches. The 6 dEQP-GLES31 SSBO compswap cases leave the hazard list (`DEVICE-READY-gles31-cas.md`).
- **2026-11-06 12:10 UTC: R32 rechecked after the build/ cleanup.** Every gate passed, and the fresh archive is
  byte-identical to sealed R32 (`release9-gate-cleanup-repair.md`).
- **2026-11-06 11:52 UTC: R32 `a3de5c91fb7` sealed** (empty dispatch + native occlusion queries).
  - Archive `69fc836b…`.
  - It rests on two hardware proofs:
    - **empty r2**: `COMPUTE-LADDER RESULT PASS`, 22/22, 0 fault lines (`DEVICE-READY-compute-empty-r31.md`);
    - **query r4** on the queryocl kernel `7bfc904d3894`: three cases copied=cpu=1152, nine jobs retired
      (`DEVICE-READY-query-native-r4.md`).
- **2026-11-06 09:54 UTC: R16 stage isolation (r11-stages1), a diagnostic FAIL as designed.** 64 cases, 77,824 bad
  pixels. R16 uploads are exact, but clears and draws are wrong; R32_UINT/R32_SFLOAT are exact. The fault is the
  narrow-format clear/EOT path (`DEVICE-READY-r11-stages1.md`).
- **2026-11-06: bug 1 (imageLoad) no longer hangs** on release9d. Native imgstore/imgload are exact and retire.
  The Zink 384/4096 stale-word fix is packeted (`DEVICE-READY-bug1-imgload.md`).
- **2026-11-06: R24 gradient focused CTS fixed 8 of 42** gradient targets. The cube controls that "failed"
  were switched off by the old exclusive selector, and R30's additive selectors fix that
  (`build/gpu/cts-r21-gradient-r24/rounds/r21-gradient-r24/`).
- **2026-11-06 ~06:40: VS ALU + dynamic shifts proven on hardware: GLES3 fail-a on Round 23 `cb499d37704` fixed 1,032 more vs R13, 0 new failures, still_failing 1,303 → 271.** shaders.operator now 769 pass / 52 refused; builtin_functions 1,430 pass / 18 refused / 11 wrong / 178 warnings. The R23 guards (GLES3, GLES2) are clean. fail-b on R18 fixed 76 (shaders.precision 64, ubo.random 12). Running GLES3 projection: about 37,970 / 42,772 (~88.8%). R24 `22f3cb1d8ef` (cube default + gradient), R25 `559fde96f0b` (FFMA modifiers) and R26 `35fca747f9f` (offset default + integer + XFB record bases) are sealed; R27 (two-bank stage B + vertex control flow) is building.
- **2026-11-06 ~05:53: vertex-texture offsets pass on hardware.** The R22 `7bf8026180c` focused CTS with `PVR_G5P_VERTEX_TEXTURE=qualified-offset` fixed 28 of 69 offset targets (texelFetchOffset 12 + sample offsets). 0 new failures, 0 refusal→wrong/crash; all 283 previously passing controls stayed Pass. The 41 still refused are grad/proj/lod offset forms. Report: `build/gpu/cts-r21-offset-r21/rounds/r21-offset-r22/report/`.
- **2026-11-06 ~05:50: cube vertex textures pass on hardware.** The R20 `0100e9bb814` focused CTS with `PVR_G5P_VERTEX_TEXTURE=qualified-cube` fixed 119 of 295, including all 90 texture.vertex.cube. 0 new failures, 0 refusal→wrong/crash; all 162 must-stay-refused controls stayed refused. The cube default (`1629cee2d58`) is released for R24. GLES3 fail-c on R18 fixed 353 more (ubo mixed-matrix packing 128, fbo.render 60, texture.mipmap 40, fbo.blit 22, builtin_variable 22), 0 new failures. Guards R17, R18, R19 and R20 are all clean (GLES3 and GLES2 each). Sealed rounds R17 `e2f31edf4e7` (ZLS), R18 `c775f8c9cb8` (integer MRT pairs on by default), R19 `64457182c3a` (R11F frontend), R20 (R21 vertex-texture default), R21 `2989852e35f` (fetch-offset) and R22 `7bf8026180c` (sample-offset); R23 is building (VS ALU + dynamic shift).
- **2026-11-06 ~04:48: GLES2 at 16,348/17,165 (95.2%)**, from the r9 base with fix-g2-02/03/r15 merged. fix-g2-r15 (Round 15) fixed 46 more: texture.mipmap 30 (linear-blit fix confirmed on hardware), fbo.render 14, shaders.functions 2, with 0 new failures. Left: named_refusal 681, not_supported 111, wrong_result 19, warning 6. Round 15 guards: GLES3 1000/1000, GLES2 1000/1000. The mrt3 rung passed its 3-target and 2-target cases. The 4-target control failed on one channel only: target 3, blue, got 255 where 24 was expected, on all 4,096 pixels. It's with the FS-store lane. Round 18 `c775f8c9cb8` (integer MRT pairs on by default) is on the device in q69.
- **2026-11-06 ~04:25: vertex textures (R21 qualified) pass on hardware: focused CTS on Round 16 `2238a7e3c31` with `PVR_G5P_VERTEX_TEXTURE=qualified` fixed 283 of 578, 0 new failures, 0 refusal→wrong/crash, 0 crashes;** the array16 witness passed. GLES3 texture.vertex 153 pass / 45 refused, GLES2 texture.vertex 45 / 45, GLES3 texture_functions 36 / 171. Every remaining case is a named refusal (cube, gradient, offset and similar forms, plus TBO, which this commit doesn't carry). Default promotion requested from the speed lane for R18/R19. Report: `build/gpu/cts-r21-qualified-r16/rounds/r21-qualified-r16/report/`.
- **2026-11-06 ~04:16: GLES3 fail-a on Round 13 fixed 591 more (shader precision 461, common 128, pack_unpack 2), 0 new failures; GLES3 coverage ~36,508/42,772 (85.4%).** wrong_result in fail-a dropped from 847 to 11; the remainder is named refusals, led by VS ALU forms (ishl 252, fround_even 84, fsign 62, fceil 36, fmul modifier 34, ffma reuse 24 = 492) and dynamic shift 378. Device rungs tonight: ZLS 37×29 sampling PASS (16 sizes), DS-passes PASS ×2, integer MRT pairs PASS (6 pairs + 2 singles), query-native r2 MEASURED-FAIL (copied=0, cpu=0). Sealed rounds: R13 bd8c596746e, R14 6954164a5df, R15 9bfba40ad2e, R16 2238a7e3c31 (R21 qualified 2D/array/3D).
- **2026-11-06 ~03:45: GLES3 coverage 42,772 cases (unrun-a-r10 adds 2,600 never-run cases): 35,917 pass (84.0%).** unrun-a-r10 alone: 1,779 pass (68.4%), 0 crashes, no fault. Its non-passes are almost all transform feedback: array_element 252 named_refusal + 126 not_supported, array 171 + 135, basic_types 36 + 72. The rate dips slightly because the new cases are XFB-heavy. XFB triage goes to the GL 3.2 lane, including whether the advertised XFB limits meet the GLES3 minimums.
- **2026-11-06 ~03:34: GLES3 on Round 10 (`68dd6bfa94a`): 34,138/40,172 pass (85.0%, up from 78.4%)** over the observed shards (r9 base with the fail-a/b/c-r10 retests merged). The fail retests fixed 519 + 806 + 96 against Round 8, with 0 new failures. Remaining: named_refusal 3,024, not_supported 1,415, wrong_result 1,302, warning 256, crash_hang 37 (the hazard set, not in these packets). Largest still-failing groups in fail-c: texture.vertex 198, shaders.loops 166, fragment_out.array 144, ubo mixed-matrix packing 128, texture.units 100. Next: Round 13 (`bd8c596746e`) replaces the Round 11 and Round 12 queues (queue q66), with both guards first.
- **2026-11-06 ~02:36: GLES3 fail retest on Round 8 (A/B/C): 1,238 of 7,241 fixed, 0 new failures** (masks/depth_stencil 621, swizzles 108, fragment_ops random/interaction 198, conversions 130, operator 57, indexing 40, ...). Biggest open: ShaderExecutor FBO-incomplete (32-bit integer RTs; RGBA32 in Round 10, R32/RG32 pending int32-rt), UBO arrays (Round 9-merged), texture.shadow depth views, VS textures (R21), VS loops.
- **2026-11-06 ~01:35: GLES2 retest on Round 7 (`a4d168a0b8b`, + FS mask-stack): 24 more fixed (shaders.indexing), 0 new failures; guard 1000/1000. Projected GLES2 16,302/17,165 = 95.0%.** Remaining: 697 named refusals (VS CF/textures/fsign/ffma-reuse lead), 111 not_supported, 36 warnings, 19 wrong results.
- **2026-11-06 ~01:13: GLES2 retest on release9-next Round 6 (`3456613e4e5`: masks, VS ftrunc, sampler arrays, R2, EBUSY backpressure, FS UBO wrap, allocator stage A): 1,136 fixed, 0 new failures. Projected GLES2 16,278/17,165 = 94.8%** (95.4% excl. not_supported), up from 88.2%. Remaining: 721 named refusals, 111 not_supported, 36 warnings, 19 wrong results, 0 crash/hang. Summary `build/gpu/cts-gles2-r9-fail/rounds/fix-g2-02/classified/summary.md`.
- **2026-11-06 night: GLES3 CTS on release9 (Round 3 Mesa, release9d): 31,482/40,172 pass (78.4%) over shards 0–313**; stopped at shard 313 by a CDM job fault (`cdm-fault`, COMPUTE-V1 ret=-5 timeout) that left render admission closed (every later submit DEVICE_LOST). Shards 314–349 unrun. Kernel robustness fix (CDM fault must not close render admission) is the first item; trigger case being identified (likely XFB via CDM). Pull `build/gpu/cts-gles3-20261105-r9/pulled/`.
- **2026-11-05 night: GLES2 CTS on release9 (Round 3 Mesa `b3132910554`, kernel release9d `07653c41`): 15,142/17,165 pass (88.2%)**, 1,874 fail, 111 skip, 36 warn, 2 device-lost (fbo.render); 135/135 shards clean. Root cause of canary3's DEVICE_LOST (source-flipped blit in the G5P CPU transfer) fixed in Round 3. Pull `build/gpu/cts-gles2-20261105-r9/pulled/`. GLES3 running.
- **Native lines (2026-11-05): `g5p-1b-dgl-native-lines@a77501da204`, 8/8 PASS.** Ordinary GL and GLES lines through Zink (Bresenham, width 1, 1×) on the A9's native LINE object: desktop 11/11 and ES 11/11 exact against the diamond-rule reference, plus the zero-factor bias no-op. This fixes the earlier named refusal of every `GL_LINES` draw.

- **Compute FMA codegen (2026-11-05): `g5p-1b-compute-fma@ab73c2b7ae6`, exact.** FMA throughput 40.8 → **104.7 GFLOP/s** (114 at large size), about 2.5×, from native inline-F32 FMA and accumulator/store coalescing.
  - wide2 did **not** reproduce wide1's +39 % bandwidth: scalar and wide are both about 8–8.8 GB/s at 64 MiB, about 45 % of the 19.2 GB/s LPDDR4-2400 peak.
  - The W278 GPU-time receipts are present on the timing1 kernel; their units aren't qualified yet.

- **c47 block 2 (2026-11-05 evening):**
  - **The compiler select-liveness fix (`850eb44a5cf`): PASS.** select1 goes 34 → 0, select32 1088 → 0, and the original indirect producer is now exact. That was the mirrored-triangle root cause.
  - **VS SSBO stores (`19242026fa2`): PASS**, on-target and fully-offscreen clipped draws included.
  - **SW-GS phase A1 (`b88e59367a9`): 4/4 PASS.** A real VS/GS/FS pipeline with the automatic compute prepass and the padded restart raster. `geometryShader` is still false.
  - **Exact public compute Mesa (`ec324199f17`): 38/38 PASS** on c47.
  - **FS stores under DS tests (dsstore `5a8b899a672`):** overlapping store draws are fixed by the TRANSLUCENT pass, and the late tests are refused by name. Store-then-later-occluder and stencil-early still fail on both arms (open; pass type 5 is the likely fix).
  - **Empty compute kernel:** the bodyless ending (`a3ab467a92f`) didn't fix the DEVICE_LOST (open).

- **Native indirect draws (2026-11-05): `g5p-1b-dgl-indirect@4c38a04156a`, 17/17 PASS.** The A9 VDM indirect packet, with compute-produced arguments, matches the paired direct draws exactly: bases, instances, multi-draw, and zero counts. The default refusal holds. firstInstance is still false.
- **Polygon modes on by default (R8, 2026-11-05): `g5p-1b-polymode@df972c09a1b`.** Vulkan 13/13 on the default driver, and GL fill/line/cull exact through stock Zink. This ends the earlier silent filled-triangle draw for `glPolygonMode`.
- **Polygon modes through GL (2026-11-05): `g5p-1b-polymode@b484b255131`.** Vulkan 13/13 PASS, and GL `glPolygonMode` through Zink PASS. GL point mode is a named known gap until GS lands.
- **Alpha-to-coverage / alpha-to-one (R9, 2026-11-05): `g5p-1b-a2c@e65d8486102`, 10/10 PASS**, using the shader-built coverage mask on the sample-mask path.
- **Hyprland arena and default tables (2026-11-05): `g5p-hypr-ram@5c68d1f0728`.** A lazy first arena chunk plus one-page default scissor and bias tables. A/B PASS on top of 84785: blur −5.5 MiB, blur-drag −4.5 MiB, stencil exact.
- **Hyprland depth/stencil sizing (2026-11-05): `g5p-hypr-ram@84785dab7fb`.** D32F_S8 is now allocated as its real 16 + 4 MiB planes, saving −10 MiB (blur) and −12 MiB (blur-drag) of Hyprland GPU buffers. The stencil test is exact at both sizes.

- **c47 retry block (2026-11-05):**
  - **The viewport-intersected ISP clip (fs-clip, `g5p-1b-fs-store@92dc3d54f43`): PASS with a real before/after.**

    | rung | 6f3e baseline | 92dc |
    |---|---|---|
    | viewport-colour | 141 bad outside | 0 |
    | viewport-store | 141 words outside | 0 |
    | scissor-xfb | 6 captured lost | 0 |

  - **Polygon modes (R8, `g5p-1b-polymode@6bc720f7f9e`): 13/13 PASS.** Native A9 line- and point-filled triangles, both culls, mixed draws and 3 named refusals.
  - **Varying capacity: 124 components interpolate exactly on A9** (`g5p-1b-varyings@afa79040e28`), against Apple's compiler cap of 60. c128 fails and is being investigated, since GL 3.2 needs 128 FS inputs.
  - **Compute wide1 (`g5p-1b-compute-wide@1c29c3f70c1`): 20/20 PASS.**
    - 64 MiB bandwidth is 8.79 GB/s with native uint4, against 6.33 scalar (+39 %).
    - FMA: 114.7 GFLOP/s at large size, against 40.9 in fixes2.
    - 2 MiB stays at about 2 GB/s (submit-bound).
  - **fma1-clip:** the fragment FMA passes with bad 0 once the inner viewport is scissored. The empty128 kernel never retires (DEVICE_LOST); that's a driver bug, owned by the compute lane.
  - **depth-feedback-1: 10/12.** Constant depth, D32/D16 reload and both bounds are exact. The gradient and perspective cases fail (1792 = 28 columns × 64).

- **Fragment-shader SSBO stores fixed (2026-11-05), the last big ES 3.1 storage gap.** Mesa `g5p-1b-fs-store@6f3e6aa5a2e`. Draws whose FS stores to memory now take the ISP scissor unless the clip ends on tile edges.
  - `zink-fs-store` gives 0/960 bad words and 0 bad pixels; guards and helper padding are exact. mixed-context and copychain32 PASS.
  - The root cause: G5P set no ISP scissor on full-attachment draws, so fragments of the edge tile beyond a 31×29 target ran and their stores landed.
  - The viewport-intersection follow-up `92dc3d54f43` (fs-clip, with a baseline arm) is next.

- **Firmware-scan readiness skip (fw-ready1, 2026-11-05).** `a9/speed-fw-ready@0e0e6d15b3a`, mode 2: a later 3D scan is skipped only when completion is already proven; TA and first scans are kept. PASS on observe, correctness and speed.
  - Per job: CPU 0.519 → 0.463 ms (−11 %), FW CPU 0.299 → 0.265 ms, scans 4.86 → 4.0.
  - Observe mode saw 0 ready→not-ready divergences.
  - Clean drag: 28.7 vs 33.0 % total CPU against pixman.
  - Not the default yet.

- **combined-bench2c (2026-11-05): labwc on the GPU now beats pixman in drag, scroll and glmark2, and uses less RAM in every row.** Kernel-cost2 cache kernel, kernel slice PASS again.

  | scenario | total CPU (GPU vs pixman) | compositor CPU | RAM |
  |---|---|---|---|
  | drag | **29.3 vs 34.2 % (−14 %)** | 12.0 vs 20.2 % | −5 % |
  | scroll | 135.7 vs 145.3 % | 8.2 vs 33.2 % | −3 % |
  | glmark2 | 54.7 vs 153.9 % | 9.8 vs 18.0 % | −45 % (387 vs 137 fps) |

  - Only idle still misses the bar: compositor 0.4 vs 0.1 %, total 14.8 vs 14.6 %, RAM −11 %.
  - The software-Hyprland arm STOPped on a proof that was too strict (aquamarine opens renderD even on llvmpipe). It's fixed in `4ea465ff9` and needs a re-run.

- **Kernel cache-maintenance fix for imported desktop buffers (kernel-cost2b, 2026-11-05).** `a9/speed-kernel-cost2@72e12f8d8673`: an explicit GEM exporter write-combined contract (ADBE opts in), plus bounded `read_va` sync. PASS on correctness and speed.
  - Per job: CPU 0.907 → 0.547 ms (−40 %), cache maintenance 0.551 → 0.178 ms (−68 %).
  - Clean drag: total CPU 29.4 vs 31.4 % pixman, compositor 12.3 vs 19.3 %.
  - Clean scroll: 135.4 vs 145.5 %, 46.5 vs 37.5 fps.
  - fw_touch, about 0.31 ms per job, is now the largest per-job item.
  - The firmware-sweep unroll gave no gain.

- **combined-bench2b (2026-11-05): labwc on the GPU now uses less RAM than pixman in every row.** Mesa `d7dde524041` (generic unsubmitted SPM skipped by default), cachemaint a59 kernel.
  - GPU vs pixman, labwc:
    - idle: CPU 14.7 vs 14.5 %, RAM 72 vs 81 MB;
    - drag: 33.6 vs 34.6 %, 86 vs 91 MB, PASS;
    - scroll: 131.8 vs 145.3 %, 142 vs 146 MB, PASS;
    - glmark2: 60 vs 154.5 %, 118 vs 205 MB, 357 vs 137 fps, PASS.
  - Only idle still misses the bar: the compositor uses 0.4 vs 0.1 % CPU.
  - The software-Hyprland arm STOPped on a harness proof bug (the renderer label is absent when the owner's config turns Hyprland's log off), fixed in `dfae4d96d`. Hyprland GPU vs software is not comparable yet.
  - The kernel-cost1 profile, idle samples excluded, puts the remaining kernel CPU at about 3.0 ms per frame:
    - dma-sync cache maintenance in `g5p_render_cache`/`read_va`, about 0.68 ms (fix in progress);
    - `g5p_rv3_fw_touch` visibility scans, about 0.31 ms;
    - the harness's own processes, about 1.0 ms.
- **Software geometry shaders, first pixels (2026-11-05).** Static point→triangle, Mesa `g5p-1b-swgs@7dafd2da997`, on c47. The geometry stage runs as a compute prepass on Mesa's common poly lowering.
  - Compute-only and graphics both PASS: GS-direct and GS-index draw 136 green pixels with bad=0, and the VS-only control is exact.
  - The three indirect cases are named refusals.
  - `geometryShader` is still reported false.
  - **The all-GPU chain PASSes too:** `g5p-1b-swgs@a0a7a696322` on `ae609f9cc636`. The VS output SSBO feeds the GS through the native same-command-buffer compute barrier (`host-access-between=0`). Direct and indexed GS give 136 green with bad=0, the VS control is exact, and the three indirect cases are named refusals.

- **Compute and graphics on one device (2026-11-05).** One shared kernel context per VM (Mesa `513b12bfad2`, plus the assertion-build fix `9c78adab9e4`) PASSes mixed dispatch/draw with teardown/recreate and RT40, with assertions live.
  - The native A9 compute→compute barrier (fixes2 `a2a6a296f66`) PASSes the copy chain; fences, single-lane CAS and the full-size benches PASS.
  - **First compute speed: 2.05 GB/s bandwidth, 40.9 GFLOP/s FMA** (host submit+fence scope).
  - Open: FS SSBO stores, 116/960 words wrong (pixels exact).
- **Hyprland arena RAM fix public (2026-11-05):** `brkosebay/mesa:g5p-perf-arena@b5009b7e2ce`, on `g5p-perf-ds-zls@beace253be3`. A lazy first arena chunk (512 KiB minimum) and one-page default scissor and bias tables; hardware A/B 2 measured −5.5/−4.5 MiB.
- **D32F_S8 ZLS-plane sizing public (2026-11-05):** `brkosebay/mesa:g5p-perf-ds-zls@beace253be3`, on the public `g5p-perf-ram3-publish@79c978f4a29`. It has the hardware-proven hypr-ram fix (−10/−12 MiB) plus a comment-only commit naming the G9P driver instead of a person.
- **WC exporter contract plus bounded `read_va` public (2026-11-05):** `brkosebay/linux:a9/gpu-pr1-wc-readva@bf64cbe325`, on the public `a9/gpu-pr1-cachemaint@55fe1ed1642`.
  - One commit: default-on, with a per-job latched policy. It touches the DRM core GEM/PRIME headers, ADBE and G5P.
  - The qualified source is flown 72e12 (kernel-cost2b and 2c PASS). The exact rebased head is unflown.
  - Upstream will need a separate case for the shared DRM part.
- **FS stores and viewport clip public (2026-11-05):** `brkosebay/mesa:g5p-pr1-fs-store@0947079961`, a new branch on the public `g5p-pr1-compute@ec324199f17`. It has 5 commits:
  1. scalar VS/FS SSBO stores;
  2. dynamic store offsets;
  3. the edge-tile scissor for storing FS;
  4. the viewport-intersected clip with clipped-draw side effects;
  5. inherited comments now name the G9P driver instead of a person.

  Option-off is byte-identical across all 165 files, and every commit was hardware-proven (fs-store-scissor, fs-clip).
- **Speed work public (2026-11-05).** Both rebased heads are unflown as exact builds; the qualified sources are a59 (kernel) and d7dde524041 plus flights 39/40/2b (Mesa).
  - Kernel: `brkosebay/linux:a9/gpu-pr1-cachemaint@55fe1ed1642` on the public `a9/gpu-pr1-compute@7d049b8e969`. It skips cache maintenance for private native-WC memory (default on, with an off switch) and adds bounded receipts. The GEM exporter contract and `read_va` stay out until combined-bench2c.
  - Mesa: `brkosebay/mesa:g5p-perf-ram3-publish@79c978f4a29`, a fast-forward from the published RAM base `7acfeb8aa97`. It brings shm-in-place, punch-through, the default-off unreachable SPM, and perf receipts. Option-off is byte-identical across all 165 files.
  - The wlroots shm-lifetime patch is held until the owner OKs the fork.
- **Merged compute Mesa public r3 (2026-11-05):** `brkosebay/mesa:g5p-pr1-compute@ec324199f17`, fast-forward over `dd14625754b`. It adds four hardware-qualified topics: bounded shader dumps, the shared VM context with the RT pool, the context-reset hook, and the native compute barrier. The combined public binary has a DEVICE-READY exact-head flight; hardware result pending.
- **Merged compute kernel public (2026-11-05):** `brkosebay/linux:a9/gpu-pr1-compute@7d049b8e969`, warm and cold flights 27/27 (cold: compute before the desktop, with no captured wake job).
- **combined-bench1 (2026-11-05), the closest to the GPU-beats-software bar so far.** Stack: ram3 + punch-through Mesa, shm-in-place labwc with the lifetime fix, and the default-on cache-maint kernel. All correctness rungs PASS, including nested Hyprland and blur.
  - labwc GPU vs pixman: idle CPU 14.9 vs 14.8 % / RAM 84 vs 81 MB; drag 33.8 vs 33.1 % / 98 vs 91 MB; scroll 135 vs 146 % / 154 vs 146 MB; **glmark2 63 vs 154 % / 133 vs 214 MB, PASS** (345 vs 137 fps).
  - Left to the bar: RAM +3–8 MB in three rows, and ≤0.7 pp CPU at idle and drag.
- **Compute barriers for odd workgroup sizes (2026-11-05):** partial2 (Mesa `22fd332895c`) pads the physical work size to 32 the Rogue way. bar33/65/97/100 are exact, with controls and indirect, 9/9, done in 193–300 µs. Still open: the bench1 bandwidth/FMA timeouts, cmpxchg@single, the FS SSBO-store compiler refusal and fences.
- **Hyprland blur on the merged driver (2026-11-05).** Punch-through (discard + depth/stencil) was ported from the old ICD: `g5p-1b-punch-ds@105a0207876`, ladder 25/25 on hardware.
  - Full-panel KMS Hyprland blur-drag ran 20 s on punch-through + ram2b (`g5p-1b-punch-ram2b@8a80d8ca8ea`) with 0/2201 resets, no failed exports and no refusals; the old refusal → guilty-reset → abort crash is gone.
  - The harness's "an export after every query" check was over-strict (frames Hyprland skipped, plus teardown) and is being corrected.
- **Kernel cache-maintenance skip for private write-combined BOs (2026-11-05).** `a9/speed-cache-maint@294d785e287`, cachemaint1 PASS.
  - Coherence is exact under both policies.
  - In labwc drag, kernel CPU falls 26.3 → 18.6 % (−29 %) and desk CPU 38.9 → 32.6 % (−16 %), at an unchanged 60 fps.
- **Merged GPU kernel public (2026-11-05):** `brkosebay/linux:a9/gpu-pr1@407b7bf2cbbe`, hardware-qualified (DEVICE-READY #4, no DFU). The RAM series is on `brkosebay/mesa:g5p-perf-s2-publish`.
- **GL/ES compute through Zink on the merged driver (2026-11-05):** an ES 3.1 `glDispatchCompute` with no override is exact (544 words, 64 guards, 248 µs).
  - Also PASS: native shared memory (static, dynamic, 2–8.5 KB), barriers up to 64 lanes, 8/16-buffer shaders, the five SSBO atomics + compare-fail, and R32UI image store.
  - Open: bar65 hangs (100/128 not reached), image load hangs, and contended cmpxchg finishes199/256; the reported1 mismatch is an aggregate reference failure.
- **Desktop GL batch 2 (2026-11-05): 14/20 units PASS on hardware,** including logic ops, sampled 4x MS, the RGBA16UI clear, default integer RTs and the named GS refusal.
  - Open: MRT8 (0/32), depth clamp 20/28, border, sample mask/shading, limits.
- **Full-screen Hyprland on the merged driver (2026-11-05):** `G5P-1B-HYPR-KMS RESULT PASS`, with the first Hyprland GPU rows.
  - The compositor's CPU is at or below pixman; total CPU is level at idle and scroll, and +58 % in drag.
  - RAM isn't comparable yet: the rows include the Omarchy shell.
  - Blur-drag crashed the compositor (being fixed).
- **Desktop GL batch 1 (2026-11-05):** device-proven conditional rendering, depthClipEnable, RGTC, cube and sync, plus integer RTs (GL 3.0 blocker, r4).
- **Compute (2026-11-05):** IRQ completion wait (190–470 µs), hardware indirect dispatch, and native shared memory all PASS.
- **First compute job on the merged driver (2026-11-04).** It ran, retired and was exact: `COMPUTE-LADDER RESULT PASS`, scalar `0x12345678`, consumed in 50 µs, retired in 1.72 ms.
  - Kernel `a9/gpu-compute-merged@14f5a250848f` (typed compute ioctl, own CDM channel, no captured programs), Mesa `g5p-1b-compute@e9aae01ed51`, unmodified firmware.
  - The fix: CDM tasks end with a generated generic END, not the reused VDM UVSW end-task.
  - **Full ladder PASS (2026-11-05 00:2x):** scalar, gid 1/8/32/64/128 and copy32 are all exact and retired, finishing in about 1.4–2.1 ms. Not yet run: shared memory, atomics, image access, indirect dispatch, Zink compute.
- **Merged driver (`g5p-1b`, no Apple bytes) runs the desktops (2026-11-04).** zink12 `ec2d8d609fb`:
  - Hyprland nested on Zink PASS ×5, with a Vulkan client presenting in it;
  - labwc nested PASS, and labwc **full-screen on KMS** presenting (fbprobe PASS);
  - the kernel close-BO leak fix (`a9/speed-close-bos@6824230ee54c`) PASSes: dead processes no longer keep arenas pinned.

  First desk-bench GPU-vs-pixman table (`build/gpu/desk-bench/20261104T211051Z-g5p1b-s2-livecheck8/`):
  - glmark2 uses half the total CPU (77 vs 155 %);
  - drag uses +80 % CPU;
  - RAM is higher in every row, from 136–215 MB of driver-pinned buffers.

  The overall verdict is FAIL against the GPU-beats-software bar. Slice 2 (RAM, drag CPU, a Hyprland arm on the merged driver) is in progress.
  Published: OrchardLinux/mesa #6 (A9 Zink desktop), #5 (G9P ES3 draft, untested on A10).
- **Discard with depth/stencil (punch-through) and Hyprland blur (2026-11-03).** Mesa `g5p-punch-ds@8150a8195df`:
  13/13 blend-ladder rungs pass on hardware, max error 1 LSB, 0 GPU events. With the owner's session on r3, blur is
  visible behind a translucent foot, with no new refusals and 0 faults.
- **Fragment programs past 16 KiB and jumps past 64 KiB (2026-11-03).** `g5p-codesize`: fs_20k, fs_100k, loop_64k and
  split_2x72k are pixel-exact on hardware, with the arena bound held.

- **GPU at 723 MHz on Linux (2026-11-03): `release8-r3`** (`a9/release8@6b0dfbfd32`, the owner's next default).
  - **Clock:** the host powers the GPC on directly at the pinned pstate (`R1+0x1000 = 0x10|q`), with the firmware
    policy words matching. The A9 firmware only applies pstate in its boot sampler, and earlier "seed" attempts failed
    on a wrong `meta+0x784` abstime offset (`experiments/perf60-clock.md`, `clock-mechanisms.md`).
  - **Ladder:** pins 200/300/400 all passed (474/550/723 MHz), 0 faults, SoC under 60 °C after 60 s of gears.
    340 → 723 MHz cut the whole-job median by only about 21 % (4.28 → 3.39 ms), so memory and sync dominate.
  - **glmark2 at 723 MHz:** most scenes run at 400–500 FPS off-screen at 800×600. ideas, terrain, shadow and refract
    fail; that's a driver-gap lane.
  - **Overclock:** above 723 MHz is built into r3 (default off; voltage params, thermal stop), not yet run.

- **Hyprland desktop at the 60 Hz cap (2026-11-03, 340 MHz).** Gears windowed under the owner's Hyprland session reached
  59.4–59.6 FPS, with 0 faults and DISPLAY PASS.
  - **Setup:** kernel `release8-mmio2` (`a9/release8@2a14037036`) with memclk state 12, `render_user_event_wake 2000` and
    `render_user_sync_range 3`, plus ICD `g5p-perf60-hypr@bc82302f291` (cut 2 clear quads and empty-job removal,
    cut 4 upload trim, cut 5 sync ranges).
  - **Steps:** 33–35 → memclk 39–40 → event wake 55 → sync range 58.5 → new ICD 59.5. Per-job time fell from 7–8 ms to
    about 5 ms (`perf60-fillrate.md` §11, `build/gpu/perf60/sDE/`).
  - **Register reads:** the GPU register licence (Apple's `isGPURegisterAccessible`: PMGR gfx on, pstate in range, R1+0
    bit 29 clear) is proven on hardware across forced parks. That covered 758 R0 reads (0 stale, 0 at nibble 0) and
    254 refused at bit 29 (`experiments/mmio-access.md`, `build/gpu/perf60/sB/`).
  - **Open:**
    - Pin ≥ 200 (474 MHz and up): the firmware only changes pstate in its boot sampler. Seeds 1/2/3 failed as decoded;
      seed 3 missed the 16 ms window by 38 ms. The fix, a stamp at the release write, is being built.
    - The `Hyprland-a9-direct` binary (one pass per frame) loads the recovery config on device.

- **Never-park Hyprland, multi-client, 16 min with 0 faults (2026-11-03, `a9/perf60-clock@d32c3acc87`).** The tuple
  is `hop 100 bell both psets8 pmctx3 cdefer`: the GPU stays powered with host doorbells at pin 100, each context
  gets its own PM record, pool and PM ID (the iOS ParamBuffer model), the PM owns its free list (`pm_once`), and a
  close is deferred while the PM's write-back still targets the closing context. Owner session plus quickshell
  (software Qt) with 8 gears runs and 16 foot open/closes: DISPLAY PASS (60 Hz vblank, 39/39 flips), gears
  31–35 FPS against 8.4 on release7. The four faults on the way there were a PM state shared across contexts, the
  PM's catalogue pages recycled by a per-job free-list rebuild, PM IDs aliasing the device PM, and a PM write-back
  into a closed slot (`experiments/perf60-clock.md`). Open:
  - pin 200 stalls in the firmware SLC3 drain, so the GPU stays at 340 MHz.
  - **Release8** (`a9/release8@38bd28cd12`, these as defaults) is on the owner's iPad with Hyprland (0 faults, gears
    33–35 FPS). The late-session memory pressure was a Mesa leak: the loader sent `apple_g5p` through kmsro, so zink
    re-imported every client dma-buf and never freed it. It is fixed in `g5p-hypr-s1fix@0a4cdcd8541`, and Shmem is
    flat across gears runs. That package is frozen in `build/release/release8/userspace`
    (`docs/release/release8-notes.md`).
- **Qt Quick on the GPU desktop uses Qt's software renderer (2026-11-03).** Qt Quick on GL caused a redraw storm, 17
  plus 5.6 jobs/s at idle. Software idles at 0 GPU jobs and 0.2 % shell CPU (`experiments/perf60-fillrate.md`
  §9.6).

- **Desktop on the GPU.** The Labwc compositor renders on the GPU (wlroots GLES2 -> Zink -> our Vulkan
  driver -> our kernel driver) and shows on the panel. Windows are composited over the background, with
  touch input. The desktop base is kernel `mcfold1` (`a9/gpu-mcfold1` @ 85ad2697fd). It runs a full
  desktop session: the Omarchy wallpaper (swaybg), waybar, foot, squeekboard, server-side title bars
  and a tap menu (`docs/gpu/experiments/logs/mcfold1/desktop-screen.png`). The clients still draw on the
  CPU (wl_shm), and Labwc composites them on the GPU.
- **OpenGL ES 3.0 on hardware (2026-11-02).** With Mesa `g5p-es3@6531e682cd3` and kernel
  `a9/gpu-desk-next@cdbd3717af` (fault isolation + MRT), the iPad reports `OpenGL ES 3.0 Mesa 27.0.0-devel` /
  GLSL ES 3.00 through Zink, with no override and 0 ES 3.0 terms failing. Transform feedback and depth-stencil
  sampling are exact, and vkcube runs on the desktop.
  - Open: Zink EGL window clients stall after frame 0 (swapchain creation fails with OUT_OF_HOST_MEMORY; a
    regression vs the WSI-fix ICD); MRT target 0 is off by 1 LSB.
  - See docs/gpu/experiments/es3.md and logs/es3/.
- **Fault isolation with in-boot recovery (hardware, 2026-11-02):** a faulting client loses only its context, and the
  GPU recovers in ~21 ms (`render_user_recover=1`) while labwc keeps rendering.
- **GPU apps in real windows (2026-11-02).** vkcube (Vulkan) and weston-simple-egl (GLES via Zink) render on the
  GPU into their own Wayland windows, and labwc composites them through linux-dmabuf. The vkcube frame matches a CPU
  reference. The fix: a vertex shader's unified store is sized from the program, like Apple
  (`2·ceil(max(temps, inputs+2)/4)`); a hard-coded 4 left registers r8+ reading as 0. Screenshots:
  docs/gpu/experiments/logs/wsi-ladder/fix-20261102/.
- **A real GPU app beside the compositor.** A textured spinning cube (vkcube's scene through GLES2 → Zink →
  our Vulkan driver), running as its own GPU client next to Labwc, at 9–12 fps. Frame 30 matched a CPU
  reference, with no faults, and Labwc kept running. The GPU was at 340 MHz (pstate 1); nothing on Linux raises it yet.
- **Transform feedback and large vertex shaders (vpds round 5, `g5p-vpds@917b4599ef8`, 2026-11-02):**
  31/31 rungs PASS on hardware. Every XFB rung passed, up to 3000 vertices captured exactly once, as did
  instancing, vertex/instance index and vertex shaders with 16–24 temps. The earlier ">12 temps wedge" and
  "IMUL broken" were one bug: vertex code set the source group bit (bit 7, "last read") on every read, so a
  second read of a freshly written register returned stale contents. It now goes only on the final read, as
  in fragments. Vertex stores must still be 4-byte (the 16-byte form is dropped in vertex tasks). See
  `experiments/xfb.md` and `experiments/vertex-temps.md`.
- **Render jobs are reliable.** Dozens of jobs in a row complete without error, fault or hang.
- **Memory map changes between jobs.** Buffers can be bound and unbound after jobs have run. The kernel
  only edits page tables in RAM and publishes a new tag, and the firmware picks it up at the next submit.
  It never touches GPU registers after a job retires.
- **Memory accounting.** A buffer mapped twice (GBM allocation and then the EGL import of the same dma-buf)
  pins its memory once. The per-app address space limit is 1 GiB and the memory limit 768 MiB. The
  Vulkan driver's memory pool grows on demand, so no fixed pool size is needed.
- **Exact rendering.** Full-panel (1536x2048) frames match a CPU reference pixel for pixel, and so do
  mixed opaque and blended draws.
- **Present path.** GPU buffers are exported as dma-bufs with fences and shown through simpledrm (which
  copies; there is no zero-copy scanout).
- **Long-run stability.** The firmware heartbeat runs for over an hour without failures.

## Problems (owner priority order)

- **CTS on the merged driver (2026-11-05, focused A10 round 1):**
  - The loader fix works: the merged ICD loads, with the API 1.4 manifest plus `PVR_I_WANT_A_BROKEN_VULKAN_DRIVER=1`.
  - **Partial colour write masks are refused by name** (`pco_g5p_general.c:4557`, Apple's class-0x88 RMW epilogue is uncharacterised). Zink then crashes on the null pipeline. It's a core GLES2 gap, and the merge lane owns it.
  - **Ordinary draws SIGSEGV in the surfaceless-pbuffer CTS path** (`buffer.write.*`) with no refusal printed. A backtrace is being collected.
- **combined-bench2e-r2 (the first complete four-arm table):**
  - labwc beats pixman on drag, scroll and glmark2.
  - Software Hyprland only reaches about 4.8 fps at about 180 % CPU, so its drag rows are invalid.
  - Merged Hyprland's RAM is +7–12 % over llvmpipe Hyprland, measured on the 2b Mesa without the hypr-ram fixes.
  - Idle fails for both compositors.

- **A confirmed compute-compiler bug (2026-11-05, hardware): one wrong value from a select inside nested control flow.**
  - Found by native-indirect-control-2 (`g5p-1b-dgl-indirect@d54cb1dafa5` on the qualified base `ae609`). The compute producer writes vertex 2's `.x` as `+0.5` where `−0.5` belongs. The CPU-seeded control is exact, and so are the other 23 words.
  - The producer has a nested if/loop with two `b32csel` (`build/gpu/orchard-indirect-base/producer-debug.txt`).
  - Owner: the compute lane (fix plus a minimal rung). Separately, the native INDEX_LIST indirect variant draws 0 pixels (`ptemp1` not populated), and the merge lane is retracing it.

1. **Desktop freeze after a few hundred frames: FIXED on hardware (6301-frame soak); a leak in our
   Vulkan driver still limits a session without the eager-arena stopgap.**
   - **Freeze, before:** labwc froze twice on an ordinary frame (seq 251 after T1, seq 339 with one
     client). The TA wait timed out after 60 s even though the firmware had posted its TA-complete event
     7–8 ms after publish. Both began as the owner started touching the screen.
   - **Freeze fix on hardware (tahang1a, boot 6e19072d, S1 touch-heavy soak):** 1262 good frames, 0 job
     errors, no timeout. 21 frames were completed by the new event rule; each would have frozen before.
     Frame gap median 0.254 s, peak 17 fps, per-frame GPU time median 66 ms (p90 255 ms).
   - **Image C on hardware (tahang1c, boot 6c7d7c70, S3):** 6301 good frames, with touch play, CPU/IRQ
     stress on both cores and a 15 keys/s burst. No timeout. 121 TAs were completed by the event rule;
     no 3D needed the 500 ms hold. Frame gap median **0.113 s**, peak **20 fps**, per-frame GPU time
     median **52 ms, p90 59 ms** (from 255 ms: completing the 3D on its event removed the long tail).
     The owner reports it's much smoother, and dragging windows stays smooth with both cores busy.
   - **New stop: a per-frame leak in our Vulkan driver (ICD), not the GPU.** At frame 1262 the driver's
     64 MiB memory arena was full (~53 KB leaked per frame). Allocations were refused, and labwc stopped
     drawing. Lead: descriptor pools never reuse GPU space for freed sets, and the arena refuses to grow
     after its first submit. A fix is being worked on (branch `g5p-arena-fix`,
     `docs/gpu/experiments/arenafix.md`). Stopgap: an eager 192 MiB arena, which lasted all 6301 frames
     of S3, so the leak with that mix is ≤ ~31 KB/frame.
   - **Next desktop kernel: `deskfold-f410c38330`** (image C + the mcfold2 kexec quiesce,
     `docs/gpu/experiments/deskfold.md`), verified offline, flying next.
   - **Cause of the freeze (`docs/gpu/experiments/tahang1.md`):** not a lost wakeup. The kernel declared a TA done only
     once the TA idle words (`G+0x724/0x728/0x72c`) read zero. The firmware sometimes leaves one set
     after finishing; it's bookkeeping that it clears at the next engine start. Everything else (stamps,
     ring, PM save) had completed. About 1 in 5 good frames showed the word set briefly; twice it never
     cleared. The 3D phase had the same bug long ago and got an event/time rule; the TA never did.
   - **Images:** `a9/gpu-tahang1`. Image A `tahang1a-ed4afeb59c` (fix only; passed S1). Image
     B `tahang1b-f9190e2a6a` (fix plus 3D completion on the firmware event). Image C
     `tahang1c-c78c0dd899` (B plus a 500 ms fallback for the 3D, so a lost 3D event can't freeze labwc).
     C replaces B for the fps test. The TA now completes on
     coherent stamps plus saved PM state plus any one of: idle words zero, the TA-complete event, or
     500 ms of continuous coherence. The test is a touch-heavy soak of ≥1000 frames.
   - Desktop speed on mcfold1, for reference: median frame gap 0.575 s, peak 8 fps, median per-frame
     GPU time 76 ms (p90 274 ms).
   - Queued, in order:
     1. 3D completion on the firmware event, removing the 200 ms retire settle: DONE (image C);
     2. partial damage / smaller render areas in the ICD, so labwc stops redrawing all 1536x2048 every
        frame (Apple's background-load program is now captured; Mesa branch `g5p-partial` in progress);
     3. GPU DVFS the Apple way (474/550/723 MHz);
     4. more than one frame in flight.
2. **Slow frames: FIXED for now with an interim workaround; the Apple-way fix is still open.**
   - Was: the firmware picked up a job within milliseconds, but the job only finished once something
     else caused memory traffic. With nothing else running, frames came on a ~20 s cycle (key to frame:
     median 7.85 s, max 27 s).
   - Cause, proven on hardware (latency123 boot 1): the firmware waits on its own root and shared pages,
     and doesn't see the update until the system-level cache line is evicted. A Normal-NC read of those
     pages from Linux makes it visible. Flushing the GPU TLBs (5.6 s), cleaning the CPU caches (3.2 s)
     or a bulk cacheable read (worse) don't fix it.
   - **Interim fix (`g5p_rv3_fw_touch()`, kernel mcfold1):** an NC read of the firmware pages, only
     while a job phase or a context bind is in flight; nothing runs while the GPU is idle. On hardware
     (mcfold1, polling off): key to frame **median 0.07 s, max 0.08 s**.
   - **Apple-way fix, still open:** iOS sets the full pstate table and the power-policy words.
     (`meta+0x6d4` was assumed to be 1; the live capture shows 0.) With `6d4 = 1` plus `policy+4 = 16`, the
     firmware accepts the first job and never starts it (boots 2 and 3). The RE
     (`docs/gpu/firmware-re/power-words-init-re.md`) blames `policy+4`: it arms the clock governor, whose
     window counts the GPU counter `R0+0x160`, which may be frozen on Linux.
   - **Bisect boot 1 (2026-11-01, latency123-405d9b96b9, `fw_meta6d4=1` only):** `6d4 = 1` alone does
     not wedge, so boots 2/3 wedged on `policy+4`. It also does not fix latency: with the interim touch
     off, key to frame was median 6.05 s, max 20.43 s (the 20 s sawtooth is back). With the touch on it
     stays at 0.07 s. Live iOS values (power capture 20261101T154856Z): `policy+4 = 16`,
     `meta+0x71c = 340`, and under stress the GPU sits in P4 = 723 MHz 72 % of the time.
   - **RE result (`docs/gpu/firmware-re/r0-160-counter-re.md`):**
     - `R0+0x160` is `ROGUE_CR_TIMER` and is not frozen. The governor window is the AIC timer.
     - The live iOS capture shows **`meta+0x6d4 = 0` in every sample**, so setting it is not the
       Apple way.
     - What Linux lacks is `policy+0x34` (0 on Linux, 1..4 live on iOS) plus the coefficient
       block. Linux also never leaves pstate 1 (340 MHz).
   - **Next:** T2, with no build: `fw_policy4=16 boot_fw_words=4a:34=1`, to unwedge. Then T3, the
     full live iOS set.
3. **Several GPU clients: stage 1 works on hardware; still root-only and never freed.**
   - **Design:** each render context gets its own VM and firmware TA/3D slot pair. The pair is bound at the
     context's first job by a DC3 command written to RAM only, with no doorbell and no MMIO. Jobs stay
     serialized on one shared channel. See `docs/gpu/multi-client-design.md`.
   - **On hardware:** labwc plus five test clients, two of them concurrent. Every frame was exact, every
     bind was consumed in 1–3 ms, the jobs interleaved, and the labwc window was unchanged. Repeated on
     mcfold1 with the latency fix and polling off (b1, then b4 ∥ b5): all exact, binds consumed in 0.8–2.5 ms.
   - **Stages 2+3 on hardware** (`a9/gpu-multiclient2@995d684abd`, first boot):
     - A closed client's slot pair, VM and pinned memory are freed, and its slots are reused only after a
       verified RAM-only unbind. In 26 open/close cycles, pinned memory returned to baseline every time.
     - Contexts are scheduled round-robin.
     - Non-root clients work: CAP_SYS_RAWIO is dropped, and the firmware window in user VMs is narrowed.
     - A stuck client job loses only its own context: the channel drains, held jobs resume, and labwc
       keeps rendering.
   - **Still open:**
     - GPU Wayland clients composited by labwc (linux-dmabuf): the second boot is running.
     - In-boot GPU recovery: built, off by default, not yet run on hardware.
     - ~~A warm kexec out of a multi-client boot.~~ **FIXED on hardware (deskfold, 2026-11-01).** The
       quiesce (`a9/gpu-mcfold2@a2ad7938e6`: unbind every slot RAM-only, then power-cycle the GPU before
       kexec/reboot; `docs/gpu/experiments/mcfold2-kexec.md`) passed both paths:
       - hop 2, manual: `unbind why=kexec slots=12 verified=12 ret=0`;
       - hop 3, automatic via the reboot notifier: `slots=6 verified=6 ret=0`.
       Both new boots came up `origin=warm-cycled failed=0` with labwc restored
       (`docs/gpu/experiments/logs/deskfold/`). **Rule (updated):** on deskfold and later, a warm kexec is fine
       after multi-client and even after a wedged, failed device. The first case was the vkcube TA
       fault on boot e46d5121: `GPU-KQ why=reboot-notifier … failed=1 wedged=1 … plan=-+cycle skip=0x18`
       skipped the detach and power-cycled, and boot eb8fab4a came up `origin=warm-cycled failed=0`.
       DFU is only needed if the warm hop itself fails.
       - Deskfold's bounded dirty start also recovers a source kernel **without** the quiesce. The
         wedged T2 governor boot (latency123, `ta=timeout/60000`) hopped into deskfold as boot
         35223fa8: `origin=warm-cycled failed=0`, labwc rendering.
       - Warm recoveries into deskfold on 2026-11-01: the multi-client hop (manual and automatic),
         two client TA faults (vkcube-a9, XFB diag `hold`) and one governor wedge (T2). Before this fix, a kexec from the T1 boot into mcfold1 never printed a line, because the
       firmware kept running from the old RAM.
4. **Sheared text and textures: FIXED (verified on hardware).**
   - Symptom: textures whose width wasn't a multiple of 16 were sheared row by row (smeared title text,
     missing terminal content).
   - Cause: the texture descriptor's stride-valid flag (bit 63 of word 1) was only set for render
     targets, so the GPU rounded every texture pitch up to 64 bytes.
   - Fix: linear image rows are aligned to 64 bytes (`G5P_LINEAR_STRIDE_ALIGN`, as Asahi does), and
     copies go through Mesa's `vk_image_buffer_copy_layout()`. It lives on the Mesa fork branch
     `g5p-upload-fix`.
   - Device ICD `a2f00cda…` with trampoline `10232194…`. Foot, the title text and a 500 px window all
     render correctly.

## Not supported yet

- **GPU Wayland clients in the desktop: work on hardware (2026-11-01).** labwc runs on the WSI ICD pair
  (`g5p-wsi`, ac0460f9/3387d083) with linux-dmabuf ON. wsi-vk and egl-wl (Zink) render on the GPU and are
  composited zero-copy (600 frames, bad=0, the window changes on screen). Open items: vkcube-wsi draws
  only its clear colour (being diagnosed), and labwc's sealed arena runs out with many windows (13
  terminals froze it; arena fix in progress, `docs/gpu/experiments/arenafix.md`).
- **Damage-only redraw is the desktop mode** (no `rerender`), and the owner sees no stale rectangles.
  While interacting: frame gap median 0.059 s (was 0.113), GPU time per frame median 47 ms, p90 54 ms.
- **Direct scanout on ADBE: works on hardware (2026-11-02)** (`a9/gpu-adbe@f6514f4528`,
  `docs/gpu/experiments/adbe-gpu.md`). The display scans out labwc's GPU-rendered buffers directly (no simpledrm,
  no CPU copy), at 60.0 Hz, with vblank IRQs at 59.9 Hz. Page flips: 107 with 106 completions, 0 timeouts, 0
  errors; a 3×60 s soak with bad=0; brightness readback OK (build/gpu/adbe/device-20261102T122034Z; the
  runner's two FAILs were checker bugs, now fixed). The GPU importing an exported buffer works. Next: make it the
  desktop base and measure frame times.
- **Partial redraws (damage tracking): work on hardware; now in use** (see above). loadOp LOAD (Apple's
  background-load program, captured and decoded on iOS) and partial render areas are on Mesa branch
  `g5p-partial` (`docs/gpu/experiments/partial-redraw.md`). On hardware the fixtures are exact, and labwc
  redraws only damage with no stale rectangles (commit `867b13dd`); per-frame GPU time 52 → 41 ms. The
  soak isn't qualified yet (no frame counter in that run), so the desktop still uses
  `WLR_SCENE_DEBUG_DAMAGE=rerender`.
- **GLES 3.0 desktop ICD: on hardware, labwc runs on it (2026-11-02, `g5p-es3@6550721a684`).** It merges cf, hypr,
  vpds, cts1 and textypes, plus the W2 swapchain fix `fe9ecdfd4d4`: 10-bit colour formats needed a LINEAR modifier.
  es3 rerun `build/gpu/es3/rerun-20261102T102245Z/`, all PASS:
  - labwc relaunched on the pair, 4180 jobs, 0 refusals or faults;
  - ES 3.0 offered with 0 failing terms, and MRT smoke exact;
  - egl-wl 600 frames with configs=16 and swapchain_errors=0;
  - weston-simple-egl draws its full triangle (the "sliver" is gone);
  - vkcube-wsi draws the full textured cube in 600 frames (~8.5 fps).

  The trampoline still refuses the punch-through pass type (discarding programs), so Hyprland's
  `rounded`/`discard` shaders need the raw ICD for now. Earlier gap tracking: `docs/gpu/experiments/gles3-gap.md`. Lanes: depth/stencil + 4× MSAA (`g5p-depth`) and formats/textures/samplers/instancing/
  queries (`g5p-gles3-tex`). Their input is the iOS captures of 2026-11-01, run `20261101T175626Z`
  (gles3, 23 scenes, plus gles3b, 45 scenes).
  - **Depth and stencil: DONE on hardware** (`g5p-depth@ed5f13dabed`, `docs/gpu/experiments/depth-msaa.md`).
    D16/D32F/S8/D32F_S8 work, as do the depth test, depth and stencil reload across passes, and depth bias,
    all 18 jobs exact (build/gpu/depth/device-20261101T212414Z). 4× MSAA is still refused: it needs
    kernel-written words.
  - **Multiple render targets: DONE on hardware.** 2 and 4 targets exact, including 4 from one varying
    (`docs/gpu/experiments/mrt.md`, `build/gpu/mrt/device-20261101T202412Z`, kernel `mrt1-96fa98d406`).
  - **Transform feedback: works on hardware** with 4-byte vertex stores (`g5p-xfb-fix`): record,
    overflow and discard are `XFB_EXACT`.
  - **Open bug, wider than XFB:** a vertex program that both fetches an attribute and writes the
    vertex/instance index wedges the TA, even for 3 vertices with no capture (ladder rung r1,
    `docs/gpu/experiments/xfb.md`). This hits any shader using `gl_VertexIndex`/`gl_InstanceIndex` with
    attributes. Fix in progress (`g5p-vpds`) from Apple's instancing captures.
- **In-boot GPU recovery works on a real wedge** (off by default). With `render_user_recover=1`, the r1
  wedge lost only its own context, the firmware restarted in the same boot in 20 ms (`GPU-RECOVER …
  ret=0`), and a new client attached and rendered exactly. Not yet checked: that labwc's next frame
  re-attaches. Once it is, turn recovery on by default.
- **Shader ISA matches A10:** G5P (A9) and Henrik's G9P (A10) produce identical words for every
  instruction form compared (`docs/gpu/hendrik/a9-reply-20261102.md`), so one compiler can serve both.
- **Hyprland on the GPU: the owner's real Omarchy session is clean on release7 (2026-11-02).**
  - **Stack:** kernel `a9/release7@802a3d4fc4` (ADBE direct scanout + vblank), Mesa `g5p-hypr-s1fix@3215220866d`
    (ICD 3f937b1c), `start-hyprland` with the owner's config, frozen by `release7-userspace.sh` (labwc-a9-adbe is the
    fallback).
  - **On the device:** wallpaper, bar (text, icons) and the launcher menu are clean over several frames, with 0
    refusals and no GPU events. Blend ladder 59/59.
  - **Fixes along the way:**
    - arena: dedicated BOs for allocations of 4 MiB and up;
    - vertex ops and source modifiers;
    - linear-to-twiddled copy_image;
    - projective sampling lowered;
    - general blending (45 proven settings by default, constants in common 0..3);
    - HSR pass type: every draw that reads the destination is TRANSLUCENT, on both the colour-only and the
      depth/stencil path. A blended OPAQUE draw read stale tile memory; that was the noise.
  - **Open:** speed. Flips are ~3.3/s and the bar is GPU-bound at 340 MHz; the GPU clock waits on D1 (`nopatch.md`).
    Memory is tight, ~135 MB available with the menu open. Details in `experiments/hyprland-gpu.md` §10–11.

## Standards (owner's rule)

Follow Mesa and Asahi (Apple AGX) driver standards and architecture as closely as possible.

- **Kernel:**
  - use the DRM scheduler (`drm_sched`) for jobs and `drm_gpuvm` for VMs;
  - explicit `VM_BIND`, with syncobj and dma-fence for synchronization;
  - shape the UAPI like Asahi's `asahi_drm.h` or mainline powervr's `pvr_drm.h`;
  - kernel coding style, checkpatch-clean;
  - no new default-off experiment variants in production paths.
- **Mesa:** follow NIR compiler conventions, use the common Vulkan runtime (`vk_*`) helpers, and keep the in-tree structure. Use
  Asahi's drivers as the design reference.
- **Where Asahi already solves something, keep Asahi's way** (owner, 2026-11-01). Imagination's Rogue driver
  (`src/imagination/vulkan/pvr_*`, csbgen) is the reference for hardware encodings and for features Asahi has no answer to,
  because the A9 GPU is PowerVR Rogue (Series 7XT).
- **Upstream:** Mesa's `src/imagination` and Asahi decline AI-written contributions. Following their standards in our private fork is
  fine, but nothing goes upstream as AI-written code.

## Rules learned the hard way

- Never access GPU registers after a job retires. If the block is power-gated, the whole SoC hangs and
  the iPad needs DFU.
- After a TA stall caused by the firmware power words (`meta+0x6d4` / `policy+4`), a warm kexec is NOT safe: the
  firmware stays wedged on the timed-out job, and the next kernel never comes up. Recovery needs DFU. Only test
  those words when the owner can do a DFU.
  (Not yet retested with the kexec quiesce below.)
- Since the kexec quiesce (mcfold2 → deskfold → multiclient2), a warm kexec out of a multi-client boot works. On
  2026-11-01 it also worked out of a boot whose TA had faulted on a client job (XFB dup:
  `GPU-KQ … failed=1 wedged=1 plan=-+cycle`, new boot `origin=warm-cycled failed=0`). The
  `EXT4 Orphan file not empty` line at shutdown is unrelated: it also appears before kexecs that work.
- Only the main orchestrator runs anything on the iPad. Agents write exact test plans instead.
- The live desktop session is valuable. Don't propose anything that ends it unless it's needed.
- Keep `PVR_G5P_GROUPS=last-read` in the session environment. Use damage-only redraw (no
  `WLR_SCENE_DEBUG_DAMAGE=rerender`) with ICDs that support LOAD/partial areas (wsi, integ/es3 and later);
  `boot-desk.sh` now defaults to that, and `DESK_DAMAGE=rerender` forces full redraws (the uploadfix-based
  `ARENAFIX=desk` ICD still needs rerender). Don't
  use the old `LD_PRELOAD` arena shim.
