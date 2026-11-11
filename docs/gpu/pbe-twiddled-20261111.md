# Twiddled PBE colour targets made the default (lane PBE, 2026-11-11)

Generated-by: LLM. Host only: no device access and nothing flown on this head.

- **Stage:** `build/orchard-0.4/g5p-stage-c0da45436a17.tar.gz`, SHA256
  **`1b4c331797e7…`** (adjacent `.sha256`).
- **Mesa:** `g5p-04/pbe-twiddled` @ `c0da45436a17a4ed78e3f164bb3a1896a7f3f76f`, on pin `3a00235254b5`.
- **Build:** compiled and packaged with lane D's recipe. Not run on the device.

## Summary

- **The gap was a gate, not missing hardware support.** The twiddled PBE store was already written,
  captured against iOS and device-proven in L11 (Mesa `61d9362d7e7` + `2e1110eedbf`, carried into R38
  and into `g5p-04/release`). It stayed behind `PVR_G5P_TWIDDLED_PBE=probe`; R38 says "no implicit
  default promotion". The release stack doesn't set the probe, so every twiddled colour target hit
  `G5P refuses: a non-linear colour target (twiddled PBE is step 7)`.
- **The change makes it the default.** It adds no new encoding.
- **"Step 7"** is the render-pass step of `docs/gpu/orchard-mesa-pr-plan.md`, section "Step 7 design"
  (`pvr_arch_g5p_gfx.c` names it "Rung A of step 7"). The twiddled PBE was left open in that step, and
  night-plan-98 later tracked it as L11 "twiddled PBE target".

## Apple findings

- **[P] PBE state for a 2D twiddled target.** 28 native iOS render captures (the observer-mapped R8/R16
  witnesses plus the earlier BGRA/RGBA ones) show the same form:
  - q0 = `(h-1)<<41 | (w-1)<<27 | key | bit 3` (bit 3 = twiddled);
  - q1 = `va>>1 | srgb<<45 | 1<<63`, with **no row-pitch field** (the linear form's stride bits are zero);
  - q2 = 0.

  R16 twiddled uses key 0x212a (the linear equivalent is 0x2122). `g5p_pbe_2d()` (`src/imagination/g5p/g5p_pbe.h`)
  reproduces all 28 rows bit for bit (`tests/pbe.c`). The captures are square 64×64 surfaces only.
- **[P] The twiddled layout is the TPU one we already sample.** POT-padded physical extent, mip chain
  offsets, and G5P layer stride (chain size rounded to 64 B, or to 16 KiB above 16 KiB) are in `pvr_image.c`.
  The PBE writes at `image + plane + level offset + layer × layer_size`, the same address the sampler reads.
- **[I] Not checked in Ghidra.** The PBE words are built by Apple's user-space Metal driver, not by the
  kext in the shared project, so the iOS captures are the Apple source here. No new iOS probe is needed
  for the 2D cases.
- **[V] On the device, as the L11 probe** (topic `2e1110eedbf`, release9d kernel, `PVR_G5P_FORMATS=probe`):
  - job 22, `dEQP-GLES3.functional.fbo.color.{tex2darray,texcube}.*`: 36 fixed, 0 new failures
    (`night-rounds-20261106.md` line 382);
  - the copy_image campaign: **all 1,051** GLES3.1 `copy_image.non_compressed` targets fixed, 0 new
    failures, guards clean (line 478). Their destinations are 2D, 2D-array and cube
    (`build/gpu/l11-copy-image-r36/twiddled-admission-summary.json`: cubemap destinations 887,
    texture2d 112, texture2d_array 52), with sources from 2D, array, cube, 3D and renderbuffers.
  - **[I]** How much NPOT and mip-level coverage those 1,051 give is not established here. The
    copy_image cases use mip-chained textures, but the census does not record which levels the admitted
    cases render into. The tail levels are exactly the 1,907 cases still refused (below).

  The native pixel oracle (`twiddled array|cube|mips`) returned rc=2 from a wrapper restore. That is not a
  numeric result.
- **[I] Not yet flown on this head.** Nothing has run on `g5p-04/release` + this commit. The code path is
  unchanged since R38 except for the gate.

## The change

Mesa branch **`g5p-04/pbe-twiddled`** in `build/third_party/mesa-04`, worktree
`build/third_party/mesa-04-pbe`. One commit, **`c0da45436a1`**, on pin `3a00235254b5`. Only
`src/imagination/vulkan/pvr_arch_g5p.c` changes:

- **Default on.** A twiddled 2D colour target is stored through the twiddled PBE (q0 bit 3, no pitch)
  unless the gate is off. This covers a mip level, one array layer or one cube face per render. LOAD and
  partial render areas use the logical twiddled image descriptor, already in the release branch.
- **Rollback without reinstalling.** `PVR_G5P_TWIDDLED_PBE=off` restores the refusal. Any other value,
  including the old `probe`, means on.
- **Remaining named refusals** (with the stale "brick" wording removed):
  - `a twiddled colour target in a 3D image (depth-plane PBE store is not qualified)`: 3D depth planes,
    iOS pack 10 (`DEVICE-READY-ios-L11-3d-slice-pbe-pack10-spec.md`);
  - `a layered twiddled colour target (N layers; one layer per render is qualified)`: layered
    rendering (one view covering several layers or faces);
  - unchanged `... with pitch ... (64-byte base, 16-byte rows)`: tail mips whose base isn't 64-byte
    aligned (the ~1,907 copy_image tail-mip cases, iOS pack 9; base mod 64 = 16/32/40). This guard
    sits after the twiddled check and still applies.

    **[I] Does an app reach it?** `glGenerateMipmap` does not. A mip-chained image is not a GPU meta-blit
    image (`g5p_meta_image()` in `pvr_arch_g5p_meta.c` needs `mip_levels == 1`), and pvr advertises
    BLIT_SRC/DST, so Zink's mip generation goes through `vkCmdBlitImage` on the CPU transfer path. It
    never reaches the PBE. Only an app that renders directly into a small tail level (an FBO attached to
    a ≤4×4 RGBA8 level) still gets a refusal, and with it a lost context.
- **A refusal doesn't hang the client.** The pin already carries the M2/M2b Zink lost-context commits:
  `63a2a7e2d25` (signal a batch's semaphores when recording failed), `e61ae956282` (keep submitting a
  lost screen's batches for their signals), `ac886ffa3c7` (new batch state after each flush) and
  `037567c6305` (keep recycling batch states on a lost screen). On integration-h2, terrain and refract
  were refused and exited with a bogus 1500–3000 fps. They did not hang; the drm_syncobj hang was the
  older o04 stack. The 18 `tex3d` cases below are the "refusal ends cleanly" control.
- **Not fixed by this change:** refract also hit `zink: couldn't allocate memory: heap=0 size=89489408`
  on the 128 MiB winsys arena (heavy-census-20261109). Once the twiddled refusal is gone, that may be
  the next thing refract hits.

## Build

One wrapper was added. `scripts/gpu/g5p-stage-at-commit.py COMMIT [--container NAME]` runs lane D's recipe at any commit
in its own container directory. It applies the recipe from `omarchy-a j71t-04/g5p-desktop`, replacing
`_commit`/`pkgver` with COMMIT and using `/orchard04/stage-<c12>`. Output is
`build/orchard-0.4/g5p-stage-<c12>.tar.gz` plus `.sha256`. The script refuses to run with under 10 GiB
free on the host or under 5 GiB free on the Docker VM disk (as an unprivileged writer sees it).

**How it was built:**

- At first the Docker VM disk was full (0 B available), and I stopped there without pruning anything.
- While I was writing this report, someone else removed the `linux-a9-*` containers (including
  `linux-a9-r39-6b` and `linux-a9-g5p-r5`). That left 20.5 GiB free.
- I then built in a container of my own, `linux-a9-pbe-build`, from the same image
  `linux-a9-vdm-zink-seed:20261108`. I removed it afterwards.

*(Device/host command block omitted; it targets the private workspace.)*

**Result:** rc=0, 1,421/1,421 ninja steps, and `pvr_arch_g5p.c` compiled with no errors. The log is
in the session scratchpad and was not kept.

**What the stage contains:**

- `libvulkan_powervr_mesa.so` reports `Mesa 27.0.0-devel (git-c0da45436a)` and carries the new refusal
  strings.
- Its file list matches `lane-d-package-stage-3a00235254b5.tar.gz`, plus `./opt/orchard/g5p/libexec/`
  and `omarchy-g5p-probe`. The current omarchy-a recipe installs that session GPU probe, from the same
  branch's `gpu-probe.c`. The shipped stage was built from an earlier recipe that didn't. It's one extra
  file; no shipped file is removed.

## Device commands (orchestrator; day flight, low hang risk)

On the device, in the unlocked G5P desktop as the desktop user. `$STAGE` is the tarball copied to
`/var/tmp/orchard04h2/`.

*(Device/host command block omitted; it targets the private workspace.)*

**dEQP subsets** (CTS-GLES on the iPad; night runner `scripts/gpu/cts/run-focus-round.py`, one process
per case, this stage against the shipped `3a00235254b5` stage, no probe selectors set):

- **Targets, twiddled layers and faces (36):** `dEQP-GLES3.functional.fbo.color.tex2darray.*`,
  `dEQP-GLES3.functional.fbo.color.texcube.*`. Exact list: `build/gpu/l11-twiddled-r2/new-admission.txt`.
- **Refusal control (18):** `dEQP-GLES3.functional.fbo.color.tex3d.*`. These must still end as a named
  refusal with no hang. Superset of both lists: `build/gpu/l11-twiddled/targets.txt` (54).
- **Mips, NPOT sizes and cube/array destinations (1,051):**
  `dEQP-GLES31.functional.copy_image.non_compressed.*`, list
  `build/gpu/l11-copy-image-r36/focus/twiddled-admitted1051.txt`. Use the existing 8 parts
  (`DEVICE-READY-l5b-copy1051-part0[1-8].md`); part 01 alone is a fair smoke test.
- **Linear guard:** `dEQP-GLES3.functional.fbo.color.tex2d.*` (single-level 2D stays linear). It must
  not change.

Pass, against the shipped stage on the same boot: the fixed count N is reported, with 0 new failures.
The 18 `tex3d` cases still end as a named refusal, and dmesg shows no fault/lost/recover line. The
proving runs set `PVR_G5P_FORMATS=probe`, and that gate still exists in the pin
(`pvr_g5p_formats.c`). Without it, formats not yet run on the device stay unadvertised, so some of the
36 + 1,051 report NotSupported rather than Pass. To reproduce the proving runs exactly, run a second arm
with `PVR_G5P_FORMATS=probe`, as job 22 did.

## Remaining time / next target

- **Unmeasured.** Terrain and refract have no GPU ms/frame yet, because they never rendered. Run the
  census above.
- **Next:** if refract then fails on the 89 MB allocation, the winsys arena cap is next. After that come
  the tail-mip 64-byte-base refusal (iOS pack 9) and 3D depth planes (pack 10).

## Lane PBE2 (2026-11-11): terrain/refract at 2 fps were glGenerateMipmap on the CPU

Generated-by: LLM. Host only: built, not flown.

- **Stage:** `build/orchard-0.4/g5p-stage-0b1b8f83d15f.tar.gz`, SHA256 **`28624b24c452…`** (adjacent `.sha256`).
- **Mesa:** `g5p-04/pbe2-mipgen` @ `0b1b8f83d15fc7895e15a2531c13e788e72b2a08`, one commit on lane PBE's
  `c0da45436a17` (worktree `build/third_party/mesa-04-pbe`). Changes `pvr_arch_g5p_meta.c` and
  `pvr_arch_g5p_layout.c` only.

### Cause (call chain)

- **[V] The app side.** Both scenes call `glGenerateMipmap` on an RGBA8 render target every frame, according to
  upstream glmark2 source: terrain in `BaseRenderer::update_mipmap()` (`scene-terrain/base-renderer.cpp:84-89`,
  after each render-to-texture pass), and refract at `scene-refract.cpp:429` (the `DistanceRenderTarget` colour
  texture, `GL_RGBA`/`GL_UNSIGNED_BYTE`, `GL_LINEAR_MIPMAP_LINEAR`). Lane PBE made these renders possible.
  Before that they were refused, so the mip generation never ran.
- **[V] The chain.**
  1. Zink has no `generate_mipmap` hook, so st/mesa's `glGenerateMipmap` uses `util_gen_mipmap`. That calls
     `pipe->blit` once per level (`u_gen_mipmap.c:127`), level N → N+1 at 2:1, and each call reaches
     `zink_blit` → `vkCmdBlitImage(LINEAR)` (`zink_blit.c:333`).
  2. `pvr_rogue_CmdBlitImage2` (`rogue/pvr_blit.c:296`) first tries `pvr_arch_g5p_meta_blit`. Its
     `g5p_meta_image()` took **only `mip_levels == 1`** images, so the call falls through to a transfer
     sub-command.
  3. That goes to `g5p_transfer_submit` (on the CPU) → `g5p_run` → `g5p_copy_aspects` → `g5p_copy`. The
     source is scaled and linear, so it takes the bilinear branch: per destination texel, `g5p_linear_sample`
     runs 4 × (`g5p_texel` → `g5p_element` + `util_format_unpack_rgba`), then one `util_format_pack_rgba`.
  4. Each util call looks up its format description through `pthread_once`. That accounts for the 51 %
     `pthread_once`, the 15 % `g5p_element.part.0` and the 17 % `g5p_copy` in the orchestrator's perf.
- **[V] The "Z24S8" symbol is an ICF alias. The formats are RGBA8 → RGBA8.** In the installed `.so`,
  `util_format_r8g8b8a8_unorm_pack_rgba_float` (0x258c40) is a 4-byte thunk (`b 0x258620`) to the
  byte-identical `util_format_z24_unorm_s8_uint_as_r8g8b8a8_pack_rgba_float`, so perf names the target. No depth
  surface is involved. A same-format copy only unpacks and packs in the scaled LINEAR branch, which pins the
  branch. Layout: twiddled mip chain, source level N and destination level N+1 of the same image.

### The fix

- **GPU (the main fix), in `pvr_arch_g5p_meta.c`.** The vk_meta blit now also takes a **twiddled 2D,
  single-layer, single-sample mip chain** (RGBA8/BGRA8 UNORM/sRGB, the existing format list):
  - vk_meta samples a one-level view (`g5p_view_state` already encodes `base_level`/`level_count` for twiddled
    images).
  - It renders one level per pass through lane PBE's twiddled PBE store, with loadOp DONT_CARE and the
    render area set to the destination rect.
  - The ordering is the existing one, read but not flown:
    - These renders are `g5p_transfer`. Their fragment signal is merged into the queue's transfer sync, and
      the next level's render merges that sync into its fragment wait (`pvr_arch_queue.c:619-628, 816-824`).
    - A CPU tail transfer waits on every in-flight job whose recorded write or read range overlaps the
      image's BO, or whose ranges are unknown (`g5p_transfer_submit`, `pvr_arch_queue.c:439-488`;
      `g5p_track_job` records each render's writes). Writing level N+1 and reading level N of the same BO
      therefore always waits.

  For each region, a destination level stays on the CPU path (unchanged) when either of these holds:
  - its base fails `g5p_job_init()`'s 64-byte colour-target guard (the same address expression), so the meta
    draw can never reach a refusal and a lost context;
  - it is under 32×32 (`G5P_META_MIN_MIP_SIDE`, one tile; the PBE captures are 64×64 and up).

  Single-level images keep their old rule exactly, and linear mip chains stay on the CPU (no mip views).
- **Rollback without reinstalling:**
  - `PVR_G5P_GPU_MIPBLIT=0` puts mip chains back on the CPU (that arm has the hoisted CPU loop);
  - `PVR_G5P_GPU_BLIT=0` puts every blit back on the CPU, as before.
- **CPU fallback, in `pvr_arch_g5p_layout.c`.** In the bilinear-blit and block-decode loops, the
  unpack/pack descriptions are resolved once per copy instead of per texel, which removes the per-texel
  `pthread_once`. The same util functions are called with the same arguments, so the output bytes are
  unchanged. This covers the tail levels and every non-meta format.
- **[I] What hasn't been checked:**
  - Mip-level views as **render targets** of a vk_meta blit are new. Lane PBE's 1,051 copy_image cases
    rendered into mip-chained twiddled textures, but nothing has run on this exact meta path.
  - The **sampled side** is also new. The source view is one level with `base_level` N > 0:
    - `pvr_g5p_tex_twiddled` puts N in q0 (`PVR_G5P_TEX_BASE_LEVEL_SHIFT`) and the last level, N, in q1,
      with the has-mips bit set;
    - `g5p_combine_sampler` then picks the single-level sampler word (no mip filter, LOD 0..14).

    That should sample level N, but I found no device record of a one-level view with base level > 0 in
    `docs/gpu`. If it actually read level 0, every level would be a downscale of level 0, and the result
    would look almost right. **The content check below is needed.**
  - On an NPOT texture (refract's target has canvas size), level N+1's twiddle order is the same question as
    rendering into level 0, which lane PBE already ships. A mismatch would show up as wrong mip content
    (blurry or garbled refraction at a distance), not as a hang.

### The 0–9 % in the other scenes (static answer)

- **[V] The shipped stack and the PBE stack differ only in the Vulkan driver.** File by file:
  - `libgallium-27.0.0-devel.so` differs in 29 bytes, the build-id and the `git-<sha>` version string, so
    Zink and the GL code are identical;
  - the only other difference is the extra `libexec/omarchy-g5p-probe` file, which no glmark2 run uses.
- **[V] Lane PBE's driver diff is confined to the `if(twiddled)` block of `g5p_job_init`.** Window-surface
  scenes (build, pulsar, ideas, ...) render linear swapchain targets, so they run the same code.
- So nothing in the code explains a loss in scenes without twiddled targets. Ideas also went up (269 → 280).
  It's most likely run-to-run or thermal noise. The A/B below settles it.

### Device commands (orchestrator; day flight, low hang risk)

The device currently has lane PBE's `c0da45436a17` stage installed. Copy the new stage to `/var/tmp/orchard04h3/`.
Run in the unlocked G5P desktop as the desktop user. Keep the SoC state the same for every arm (read it as the h2 SOC
pass does; 12 vs 13 moves glmark2 by 24–43 %), and record it per arm.

*(Device/host command block omitted; it targets the private workspace.)*

Census script assumptions: the on-device `glm-census-g5p.sh` isn't in this tree. I've assumed that it keeps
`glm-census.sh`'s `SKIP` handling and that it passes environment variables such as `PVR_G5P_PERF_LOG` and
`PVR_G5P_GPU_MIPBLIT` through to glmark2, since it only exports labwc's G5P variables on top. If `SKIP`
isn't honoured, the runs still work; they just take longer.

The device keeps the new stage installed at the end of step 4. To roll back to lane PBE's stage, extract it over
(`inst $H/g5p-stage-c0da45436a17.tar.gz`, if it is still on the device). To roll back to the shipped stack, use the full
rollback above.

**Expected results.** These are bounds, not predictions:
- **terrain:** GPU ms/frame was 23.8 at 2 fps, so it can reach **≤ ~42 fps**;
- **refract:** GPU ms/frame was 13.6, so **≤ ~73 fps**.

GPU ms/frame rises a little from the blit renders: the levels add about ⅓ of level 0's pixels, all at 2:1
with DONT_CARE load. Each frame also gets one GPU→CPU→GPU round trip per `glGenerateMipmap`, for the
CPU tail (below). Pass criteria:
- the proof run shows `gpu-blit` lines, no refusal and rc 0, and fps far above 2;
- the `cpu-mip` arm is slower than the new default but above 2 fps (the CPU hoist alone);
- the other scenes are equal between the `-new` and `-shipped` arms within the spread between the two runs
  of each.

### Remaining time / next target

- **The CPU tail is a sync bubble.** Levels under 32×32, or with a base that isn't 64-byte aligned (the
  1×1/2×2/4×4 tails), are still CPU transfers. The transfer submit **CPU-waits** for the last GPU level's
  fragments, does a few hundred texels, then signals, which serialises the queue once per `glGenerateMipmap`.
  Next target: draw the tail levels on the GPU. That needs the tail-mip 64-byte-base rule (iOS pack 9),
  i.e. how Apple places or stores sub-64-byte levels.
- **Per-level render jobs.** About 5 jobs per 1024² chain. If job overhead shows up in GPU busy %, the
  next step is Apple-style mip generation in fewer passes.
