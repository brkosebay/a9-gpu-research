# Lane B2: going beyond Apple — fp16, co-issue, texture scheduling, pass merging (2026-11-09)

Generated-by: LLM (Lane B2, read-only study + spec). No device step was run and no driver source was edited.

Inputs: `lane-b-alu-codegen-spec.md` (not published) and [microbench-gap-20261109.md](microbench-gap-20261109.md).

Evidence tags: **[V]** = read in Apple's compiler output, our code, or public source; **[I]** = inferred.

Reproduce the Apple side (host only): `scripts/gpu/laneb2/probe.sh`. It compiles `scripts/gpu/laneb2/b2probe.metal` with
`metal-tt -arch applegpu_g5p` into `build/laneb2/probe/split_g5p/` and prints instruction counts by class byte.

## 0. Ranking

| # | Item | Expected gain | Confidence | Risk |
|---|---|---|---|---|
| 1 | **Pass merging / pass count** (§4) | Unknown until counted. Each avoided full-screen pass saves one job floor (≈1.3 ms now, ≈0.16 ms after Lane A) plus one 12.6 MB tile store (≈1 ms on iOS, `clear_store`). | Mechanism [V], opportunity unmeasured | Medium (render-pass state) |
| 2 | **Texture-sample batching** (§3, spec in §5) | `tex_sample fetches=4`: ≤ 0.3 ms (7 of 38 instructions, 3 of 4 waits). Larger on multi-tap blurs and on high-register shaders where occupancy can't hide 4 round trips. | Codegen gap [V], timing [I] | Low |
| 3 | **fp16 / mediump** (§1) | **0 % on the current benchmark set.** Apple's half code has the same instruction count and bytes as fp32; WebRender fragments and Aquarium's main shaders are highp. Up to 2× on ALU-bound mediump shaders **only if** `alu_half` on iOS shows a faster half issue rate. | [V] density, rate unknown | Medium (precision) |
| 4 | Kept-loop overhead (Lane B F3, not new) | ≈ 2.4× on loops F1 doesn't unroll (blur loops with runtime counts) | [V] | Low |
| 5 | **Dual issue / co-issue** (§2) | **0.** One operation per instruction in every Apple probe. There's nothing for a scheduler to pair. | [V] encoding; dynamic dual issue [I], test in §6 | — |

## 1. fp16 throughput

### 1.1 What the A9 issues for half math [V]

Each pair below has the same body in `float` and `half` (16-trip loops, so Apple fully unrolls them):

| Probe (Apple, applegpu_g5p) | fp32 | fp16 |
|---|---|---|
| `fma` (16 × vec4 fma, shared constants) | 69 instr / 1040 B: `9e`×60 + `8a`×4 | 69 instr / 1040 B: `8e`×60 + `8a`×4 |
| `muladd` (`a*m+c`, fast-math fused) | 69 / 1032 B | 69 / 1032 B |
| `ilp` (two independent vec4 chains) | 137 / 2096 B | 137 / 2096 B |
| `comp` (clamp + mul, compositor-like) | 69 / 812 B | 69 / 834 B |
| `tex4` (4 bilinear samples, sum) | 31 / 246 B (`1a` f32 samples) | 31 / 246 B (`18` f16 samples) |

- **No packed 2×f16 and no shorter encoding.** A half FMA is the same 16-byte instruction with opcode `0c` instead of
  `4c`, and one scalar per instruction. Example: `8e01000109810041110100410c017000` vs fp32
  `9e010001098d0041190100414c017000`. Destinations count in 16-bit halves (`8e0103…` writes half 3). [V]
- **What half does save:**
  - Register footprint is halved (two values per 32-bit register), which can raise occupancy.
  - Iterators use the narrow form (`0a13…` instead of `0813…`), at the same instruction count.
  - Samples use the f16-result form `18` instead of `1a`, which halves the result registers.
- **f32↔f16 conversion is free at operand level [I: field meaning inferred].** `f_fma16r` reads f32 push constants into half FMAs (`8a…4041…40410c`)
  with no conversion instructions; the narrowing sits in source/result controls. Lane B already uses the result side
  (`rh_half`). [V]
- **Unknown offline: issue rate.** We can't tell from the code whether `8e` issues faster than `9e`. Imagination's
  Series 7XT marketing claims 2× FP16 FLOPs per clock [I, public material, not verified on A9]. If that holds, it must
  come from a faster per-instruction rate, because the instruction count is identical. Only a device measurement
  decides (§6, `alu_half`, **needs an iOS session**).

### 1.2 What Safari/ANGLE does with `mediump` [V]

- **ANGLE's Metal translator never emits `half`.** `src/compiler/translator/msl/UtilsMSL.cpp:29`
  (`case EbtFloat: return "float";`) and `EmitMetal.cpp:975` print `float` whatever the precision. Precision is used
  only to pick `metal::precise::tanh` for highp (EmitMetal.cpp:494), and `TranslatorMSL.cpp:1406` sets
  `validatePrecision = false`.
- **So Apple's own WebGL path runs `mediump` as fp32.** Lowering mediump to f16 would be "beyond Apple" for WebGL.
- **Caveat:** that WebKit on iOS 16 uses this translator is [I]. We have no WebKit binary in our captures; the claim
  rests on ANGLE's public main branch.

### 1.3 Does mediump reach our compiler? [V]

| Path | Mediump survives? | Evidence |
|---|---|---|
| Firefox WebGL on aarch64 Wayland | **Yes.** `gfx.egl.prefer-gles.enabled` defaults true on `MOZ_WIDGET_GTK && MOZ_AARCH64` (StaticPrefList.yaml:8009), so the context is GLES and the shader output is `SH_ESSL_OUTPUT` (WebGLShaderValidator.cpp:87). | gecko-dev |
| Mesa GLSL → 16-bit ALU | **Only if the driver reports fp16 + int16.** `glsl_parser_extras.cpp:~2503` runs `lower_precision` for ES shaders when the `fp16` or `int16` shader cap is set; `gl_nir_linker.c:1365` lowers mediump temporaries only with both. Zink sets `caps->fp16` from `shaderFloat16` (zink_screen.c:636). | local Mesa tree |
| Our driver | **Blocked today.** `pvr_physical_device.c:323` `.shaderFloat16 = false` (also `shaderInt16`, `storageInputOutput16` false). The backend refuses 16-bit constants (`pco_g5p_general.c:6689`, `refuse(c, "%u-bit constant")`) and has no general 16-bit ALU path; the half forms are used only for narrowed results (`rh_half`) and blend templates. | `mesa-g5p-laneb-f1f2` |
| Zink varyings and samplers | Zink's `nir_to_spirv` decorates mediump inputs, outputs, samplers and images with `RelaxedPrecision` (nir_to_spirv.c:990/1357/3144/4366); `spirv_to_nir` maps that to `GLSL_PRECISION_MEDIUM` (vtn_variables.c:1367). ALU results aren't decorated, so `mediump_16bit_alu` never triggers. | local Mesa tree |

### 1.4 Which benchmarks would benefit [V]

- **WebRender:** fragment shaders declare `precision highp float;` (`res/base.glsl:61`). Only about 45 varyings are
  explicitly `mediump`, mostly colours (`ps_quad.glsl:44`, `ps_text_run.glsl:7`, `composite.glsl:43`).
- **Aquarium:** the fish, seaweed, diffuse, normal-map and reflection shaders use
  `#ifdef GL_FRAGMENT_PRECISION_HIGH precision highp float;`, and Firefox defines that macro
  (WebGLShaderValidator.cpp:172). So they run as **highp**. Only `texFragmentShader` and `laserFragmentShader`
  are mediump.
- **Conclusion:** on the current benchmark set, fp16 ALU lowering touches almost no hot arithmetic. **Gain ≈ 0 %**
  whatever the hardware half rate.
- **Remaining small lever** [I, unmeasured]: mediump colour varyings could iterate narrow (`0a`) and mediump samplers
  could return f16 (`18`), halving those registers. It's an occupancy effect; quantify it only after `alu_regs`
  (§6) shows occupancy matters.

### 1.5 Spec, if `alu_half` on iOS shows a faster half rate (not before)

The precision rules are the GLSL ES 3.00 §4.5 minimum for mediump: relative 2⁻¹⁰, range ±2¹⁴.

1. **Device features.** `pvr_physical_device.c`: set `shaderFloat16` and `shaderInt16` true **for G5P fragment use
   only**. This is a whole-device feature, so the compiler must then accept 16-bit ALU in every stage. Until the vertex
   stage has witnesses, refuse 16-bit in VS by name (the "proper support, no bypass" rule) rather than claim the
   feature. This is the hard part; it needs owner sign-off, since claiming `shaderFloat16` without full support would
   be over-claiming.
2. **NIR.** Nothing is needed in our pass list: Mesa's GLSL `lower_precision` already turns mediump into
   `float16_t`/`f2f16`/`f2f32` NIR for ES shaders through Zink. Add `nir_opt_16bit_tex_image` and
   `nir_fold_16bit_tex_image` (so mediump samplers return f16 → `18`), and `nir_lower_mediump_io` for FS inputs that
   are `GLSL_PRECISION_MEDIUM` (narrow `0a` iterators).
3. **Backend** (`pco_g5p_general.c`):
   - accept `bit_size == 16` defs in the allocator, holding a half index (the existing `rh_half` machinery is the
     template);
   - emit `8e`/`8a` (FMA, opcode `0c`) and class-99/89 `04`/`08` (add/mul f16, ISA notes §ALU);
   - turn `f2f16`/`f2f32` into source/result controls, not instructions (Apple's `f_fma16r` form);
   - byte-witness each form against `build/laneb2/probe/split_g5p/*f_*16*`.
4. **Precision guard.** Apply f16 only to values whose NIR came from mediump (Mesa's lowering already guarantees that).
   Never demote highp, and never use a driver-side "relaxed" switch. Derivatives of f16 values: Zink reports
   `fp16_derivatives = false` (zink_screen.c:634), so Mesa keeps derivative inputs at 32-bit.

## 2. Dual issue / co-issue

- **Encoding [V]:**
  - Every Apple probe issues one operation per instruction.
  - `f_ilp32`: 128 independent FMAs → 124 `9e` + 4 `9a`, i.e. 128 instructions. Two independent chains are never
    packed together.
  - `f_mixint` (fma + xor + shift + and per element, 256 ops) → 264 ALU instructions, one per op.
  - `f_mixsfu`: FMA, add and `rsqrt` are all separate instructions; there are more instructions than source ops.
  - The parcel framing (continuation bit 8, ISA notes §Parcel framing) has no group header that carries several
    ALU slots, unlike Rogue's instruction groups (`pco_isa.py` phases P0/P1/P2/backend).
  - Henrik's G9P encoder (`g9p_isa.h`, `g9p_a9_alu.h`) has no co-issue concept either.
- **Schedule evidence [V]:** Apple runs each component's 64-FMA chain back to back without interleaving (Lane B §2).
  Its scheduler doesn't arrange independent work for pairing.
- **Rate evidence [V]:** Lane B measured about 1 issue slot per instruction for MOV, branch and FMA alike (ours 103 vs
  Apple 89 G thread-instr/s).
- **Expected gain from a pairing scheduler: 0.** No spec.
- **Open [I]:** the hardware could still dual-issue consecutive independent instructions dynamically. `alu_mix` in §6
  tells: if mixed int + fp costs the max of its parts instead of the sum, a scheduler that interleaves int and fp
  work would gain. Linux can run it today; iOS is optional.

## 3. Texture fetch scheduling

### 3.1 Batching [V]

| Shader | Apple | Ours (`laneb-alu/ours/tex4.k1.usc`) |
|---|---|---|
| `tex4` | 31 instr: iter, wait, **6 coordinate ALU ops into adjacent pairs, 4 samples, one `4d00`**, adds, narrow `×0.25` | 38 instr: **sample, `4d00`, adds** ×4; `mov.reg` per coordinate (non-adjacent pair); `mov.imm 0.25` + 4 narrow `fmul` |
| `blur9` (9 taps, f16) | samples in batches of **4 then 5**, one `4d00` after each batch (3 waits incl. the iterator) | — |
| `tex2v` (two varying-coord samples) | `iter, sample, 4d04, iter, sample, 4d00` — **`4d04` is a new wait control, unresolved** | — |
| `texdep` (dependent read) | `sample, 4d00, sample, 4d00` (required) | — |
| `tex1` | `iter(ext 0080), sample(18), 4d00, emitpix, end` | byte-identical (Lane B) |

**Cause in our code [V].** `emit_tex()` (`pco_g5p_general.c:4761`) puts `g5p_usc_wait(raw, 0)` immediately after
every `g5p_usc_sample` (:4812). It also frees the iterated coordinate (`c->busy &= ~…`) right after the sample, which
is only safe because of that wait.

**The template already exists [V].** The dependent-read-counter batching for coefficient loads (`struct drc`,
`drc_take`, `drc_flush`, ~:3958) issues up to 8 reads on counter 0, then 8 on counter 1, with one wait per counter.

### 3.2 PDS "DOUTI iterate-and-fetch" [V]

- **Not available on A9.** Rogue's `DOUTI` (`csbgen/rogue/pds.xml:197-230`) is "only legal in a coefficient loading
  program". Its fields are depth bias, primitive ID, shade model, point sprite, wrap, size, `f16`, perspective and
  offsets. **There is no texture-issue field.** The pre-shader texture read was an SGX feature.
- **On A9** the PDS loads coefficients and the USC interpolates (`iter`, class 08).
- Apple's closest equivalent is the iterator extension `0080`, which chains iterate → sample with no wait in between
  (`f_tex1`, `f_tex2v`, `f_texdep`). We already emit it (`g5p_usc_coord_iterator`).
- **Nothing to gain here.**
- **Side note [V]:** DOUTI has an `f16` bit and an `f16_offset` ("offset within vertex taking into account the F16s
  and F32s present"), so the TA can store varyings as f16. That would halve parameter-buffer varying traffic for
  mediump varyings. It's untested on A9 and belongs with §1 if fp16 ever goes ahead.

### 3.3 Is our `tex4` really bilinear?

- **Why ask.** Our measured `tex4 − tex1` increment (0.36 ms) is below iOS's (1.04 ms). That's too good to trust.
- **Setup.** Both microbenches sample a 1024² RGBA8 LCG-noise texture (`microbench.c:340-344`; seed `0x12345678`,
  `x = x*1664525+1013904223`) with LINEAR/LINEAR, mipmap NEAREST, REPEAT and `maxLod 0` (`microbench.c:355-356`). That
  matches Metal's `filter::linear, address::repeat`.
- **Why noise works.** With per-texel noise, bilinear at a 1.5-texel offset differs from NEAREST by tens of LSBs on
  most pixels, so the check is decisive.
- **Spec it before any texture speed claim** (in §6 as `--check tex`).

## 4. Pass merging and on-chip intermediates

### 4.1 What we do today [V, file:line in `build/third_party/mesa-g5p-laneb-f1f2/src/imagination/vulkan/`]

- **Render-pass objects.** Upstream Rogue subpass merging runs (`pvr_arch_pass.c:1054`, `disable_merge=false`;
  `pvr_arch_hw_pass.c:1920` `pvr_merge_subpass`, :1611 on-chip `output_reg`/`tile_buffers`).
  - G5P's job setup ignores the merged state. `pvr_arch_g5p_job_init` (`pvr_arch_g5p.c:625`) reads only
    `eot_surfaces`, `color_init` and `sample_count`. No G5P file reads `hw_render->subpasses`, output registers or
    tile buffers.
  - **Latent correctness bug (flag only, not in scope):** a multi-subpass pass that upstream merges, especially one
    with input attachments, is very likely wrong on G5P.
  - Zink never creates such passes (below), so the desktop doesn't hit it.
- **Dynamic rendering.** It is advertised (`pvr_physical_device.c:136,579`). Each `vkCmdBeginRendering` becomes
  exactly one HW render (`pvr_arch_cmd_buffer.c:4998`, :4402-4613). There is no merging across consecutive
  Begin/End pairs, except upstream's SUSPENDING/RESUMING continuation (:5013-5022).
- **Load/store.**
  - Depth/stencil `DONT_CARE` store is honoured (`zstore` only on STORE; `pvr_arch_g5p_ds.c:103-106`). The
    `ds_load` hook drops loads for aspects that are neither stored nor tested.
  - A colour `DONT_CARE` store becomes a 16×16 null target (`pvr_arch_g5p.c:640,714-723`).
  - A colour CLEAR uses clear colours, not a load. A partial render area forces LOAD (:829-833).
  - `STORE_OP_NONE` is not exposed.
- **Transient attachments.** There is one memory type (DEVICE_LOCAL | HOST_VISIBLE | HOST_COHERENT,
  `pvr_physical_device.c:1258`). There is no LAZILY_ALLOCATED type, and `TRANSIENT_ATTACHMENT` is unused.
- **MSAA.** Dynamic rendering resolves 4× on-chip in the PBE (`pvr_g5p_image.c:233`). Render-pass objects can't,
  because there is no `gs_rta_support`.

### 4.2 What Zink sends [V, `src/gallium/drivers/zink/`]

- **Dynamic rendering is mandatory** (`zink_device_info.py:216`). So every GL framebuffer bind or flush is its own
  `BeginRendering`, and render-pass-object merging never applies.
- **Load ops.** LOAD if the resource is valid, CLEAR if a clear is pending, otherwise DONT_CARE
  (`zink_context.c:3410-3413,3505-3529`).
- **Store ops.**
  - Depth invalidate (`glInvalidateFramebuffer`, which WebRender issues) → depth `STORE_OP_DONT_CARE`
    (`zink_context.c:3448`). The imagination driver ID enables `track_renderpasses`
    (`zink_screen.c:3340-3347`). So depth already stays on-chip.
  - A colour invalidate is honoured only when the pass has a resolve (:3416).
- **No transient depth.** Zink never sets `TRANSIENT_ATTACHMENT`; its LAZY heap exists but is never chosen.

### 4.3 Where the time could be

- **Load/store bytes are not the lever.** `load_action load`, `clear` and `dontcare` cost the same on both stacks
  (2.79/2.77/2.89 ms ours; 1.03/1.01/1.02 iOS). [V, microbench-gap]
- **The lever is pass count.** Each avoided full-screen pass saves:
  - one job floor: ≈1.3 ms today, ≈0.16 ms once Lane A lands;
  - one tile store: iOS `clear_store` = 1.03 ms for 12.6 MB, ≈12 GB/s.
  - Sum: up to **≈2.3 ms per avoided full-screen pass today**, ≈1.2 ms after Lane A. [I]
- **Where merging could come from** [I]: consecutive `BeginRendering` on the **same attachments**, with LOAD after
  STORE and nothing in between that reads or writes them. Zink starts a new pass for each of these:
  - a flush;
  - a query begin/end;
  - an upload that its unordered command buffer couldn't hoist;
  - a `glBlitFramebuffer` to another target.

  A driver-side merge ("No Zink modifications" rule) would join such pairs into one HW render inside a command
  buffer: drop the first pass's store and the second's load, and keep a single EOT.
- **What doesn't qualify.** WebRender's picture-cache tiles each target their own texture, followed by one composite
  to the backbuffer. Those can't merge.
- **So the opportunity is unknown until counted.** Count first (§5.2), then decide.
- **Skip-empty-tiles.** r39-11 (in `third_party/orchard-mesa-r39-9-perf` and `-recovery-safe`, **not** in the f1f2
  tree) clears ISP `PROCESS_EMPTY_TILES` for single-sample, colour-LOAD passes whose stored depth/stencil is also
  loaded.
  - A merged pass is still a LOAD pass, so the two compose.
  - Merging removes whole passes; skip-tiles removes untouched tiles of the passes that remain. They don't overlap.
  - On partial-damage desktop frames, skip-tiles is probably the bigger lever. Measure it first: its device run is
    still pending.

## 5. File-level specs (Codex: "no new tests, no gates, build and stop")

### 5.1 Spec A — batch independent texture samples behind one wait

**Base.** The orchestrator picks it (written against `mesa-g5p-laneb-f1f2@819833730a2`; line numbers refer to that tree). **File:** `src/imagination/g5p/pco_g5p_general.c`
only.

1. **State in `struct gctx`:**
   - `uint64_t tex_pending;`: register mask of sample destinations still in flight;
   - `uint64_t tex_coord_pending;`: coordinate registers that the in-flight samples still read;
   - `unsigned tex_batch;`: samples since the last wait.
2. **New `static void tex_flush(struct gctx *c)`:**
   - if `c->tex_batch`, `put(c, raw, g5p_usc_wait(raw, 0), "wait")` (counter 0, `4d00`, the only control Apple uses
     after samples);
   - then `c->busy &= ~c->tex_coord_pending` (see step 3);
   - then `c->tex_pending = c->tex_coord_pending = 0; c->tex_batch = 0;`.
3. **In `emit_tex()` plain path (:4761-4824):**
   - Before allocating, call `tex_flush(c)` if `c->tex_batch == 4`. The witnessed batch sizes are 4 (`tex4`) and 5
     (`blur9`); cap at 4. The 8-read DRC limit is for coefficient reads and is [I] for samples.
   - Replace the trailing `put(… g5p_usc_wait(raw, 0) …)` (:4812) with
     `c->tex_pending |= BITFIELD64_RANGE(dst, 4); c->tex_batch++;`.
   - Defer the coordinate free: instead of `c->busy &= ~BITFIELD64_RANGE(coord, 2)` right after the sample, add the
     range to `c->tex_coord_pending`. `tex_flush` frees it. Allocate `dst` while the coordinate is still busy.
     Computed coordinates that are SSA values (no scratch copy) must not be overwritten while pending, so add their
     registers to `tex_coord_pending` too, and flush in the allocator if it would hand one of them out.
   - Keep the immediate wait (call `tex_flush` straight after the sample) for the `narrow` path (output-direct `18`
     form, which is byte-identical to Apple) and for `emit_tex_ext`, `emit_size` and the vertex paths. **Only the
     plain f32 fragment sample is batched.**
4. **Flush points.** Call `tex_flush(c)`:
   - at the top of `reg_of()`/`resolve_value()` when the referenced value's register is in `c->tex_pending`
     (a read of a pending result);
   - in `alloc_reg()`/`alloc_run()` when `c->tex_pending` is non-zero and free registers run out, before the
     allocator would refuse;
   - before every control-flow emit (`emit_if`, `emit_loop`, branch/jump helpers);
   - before any memory load/store, iterator or coefficient batch (`drc_*`), `emitpix`/output, discard and end.

   Simplest correct rule: flush in the main instruction loop (:6613 dispatch) before **any** instruction whose sources
   include a pending register, and before any non-ALU instruction other than another plain `nir_tex_instr`.
5. **Coordinates into adjacent pairs (optional, same patch).** When the coordinate is computed, the existing
   `mov.reg` ×2 path (:4795-4799) fires because x/y aren't adjacent. Apple writes coordinate ALU results straight
   into adjacent pairs. Leave this alone unless it falls out of the allocator's `prefer`; it is −2 instructions per
   sample.
6. **Expected bytes.** `tex4.k1.usc`: 4 samples followed by one `4d00`, about 32-34 instructions (Apple 31). Check with
   `scripts/gpu/laneb-alu-compare.sh` after relinking the CLI (Lane B §6). `tex1` must stay byte-identical to Apple.
7. **Don't touch:** `4d04` (unresolved), counter 1 for samples (no witness), or the `narrow` path.

**Expected gain.**
- `tex_sample fetches=4`: −7 instructions/pixel ≈ 22 M thread-instructions/frame ≈ 0.2 ms at our measured
  100 G/s, plus latency overlap (3 fewer full sample round trips per thread). **≤ 0.3 ms**, possibly 0 on this
  full-occupancy bench.
- The real target is multi-tap shaders: WebRender `cs_blur` and `brush_*` with several samples, and Aquarium's
  normal-map + reflection shaders, where register pressure limits occupancy.
- **Measurable only with GPU timestamps (Lane A).** Fence-wall noise is about ±0.15 ms.

**Risk.** Low. It's a local change in one function, with explicit flush points. The failure mode is a missing
flush: a read before the data arrives. That most likely gives a wrong colour, not a hang [I]; USC read-before-write
behaviour isn't characterized. The CTS texture groups in the night queue cover
it.

### 5.2 Spec B — count passes before merging anything (instrument, then decide)

**File:** `src/imagination/vulkan/winsys/apple_g5p/g5p_ws_perf.c` (`PVR_G5P_PERF_LOG=2`, one line per job), fed from
`pvr_arch_g5p.c` job init.

1. **Per-job fields.** Add to the `=2` line, from the G5P render-job description built in `pvr_arch_g5p_job_init`:
   - `w×h` of the render;
   - number of EOT surfaces and the colour load (LOAD/CLEAR/DONTCARE from `color_init`);
   - depth/stencil load and store bits (`zload`/`zstore` from `pvr_arch_g5p_ds.c`);
   - the first EOT surface's GPU address (a 64-bit hex value; this identifies "same attachment").
2. **Merge candidates.** Add a running counter `merge_candidates`, incremented when this job's first EOT address and
   size equal the previous job's, its colour load is LOAD, and the previous job stored. Print it in the `=1`
   120-job summary.
3. **No behaviour change.**

**Decision rule** (orchestrator, after one desktop run and one Aquarium run):
- `merge_candidates / jobs < 5 %` → drop pass merging.
- Otherwise spec the merge in `pvr_arch_cmd_buffer.c`: on `CmdBeginRendering`, if the previous rendering in this
  command buffer had identical attachments and render area, the store/load ops chain (STORE → LOAD), and no barrier,
  transfer or compute was recorded in between, reopen the previous `hw_render` instead of starting a new one. That's
  the SUSPENDING/RESUMING machinery at :5013-5022, applied implicitly.

## 6. Microbench additions and device commands

### 6.1 New tests (both tools, same names and output format)

| Test | iOS (`tools/ios-gpu-microbench/microbench.metal` + `.m`) | Linux (`tools/linux-gpu-microbench/*.frag` + `microbench.c`) | Decides |
|---|---|---|---|
| `alu_half mads=64_fp16x4` | `f_alu_half`: copy of `f_alu` with `half4 a`, `constant half4* k` (8-byte constants), returns `half4` | `alu_half.frag`: `#extension GL_EXT_shader_explicit_arithmetic_types_float16`, `f16vec4`; **unsupported today** (`shaderFloat16=false`; 16-bit refusal at `pco_g5p_general.c:6689`). Query `VkPhysicalDeviceShaderFloat16Int8Features` first; if `shaderFloat16` is false, print `MB alu_half unsupported` and skip. Don't request the feature at `vkCreateDevice`, or the whole binary fails. | Half issue rate (§1) |
| `alu_ilp mads=64_fp32x4x4` | `f_alu_ilp`: 4 independent float4 chains of 16 FMAs each (same 256 FMAs/px) | `alu_ilp.frag`, same body | Latency-bound vs issue-bound |
| `alu_mix ops=64x(fma+xor)` | `f_alu_mix`: per trip `a=fma(a,m,c); x=(x^s)+(x>>1)` on float4/uint4; also run fma-only and int-only halves | `alu_mix.frag`, same | Dynamic dual issue (§2): cost ≈ max → yes, ≈ sum → no |
| `alu_regs live=4/16/32` | `f_alu_regs<N>`: same 64 FMAs, plus N live vec4 values kept to the end and summed into the output | `alu_regs.frag` with `-DLIVE=N` (as `tex.frag` does `FETCHES`) | Occupancy sensitivity, which bounds any fp16 register-saving gain |

- **Constants.** Push constants for Linux (as `alu`), `setFragmentBytes` for iOS. Use the same values as `alu`
  (`0.999…`, `0.001…`); the half variant uses `__fp16` of the same values.
- **Rates.** `pix*64*4*2/1e9` GFLOP/s for all `alu_*` tests (`alu_mix`: report Gop/s, counting 3 ops per component
  per trip).

### 6.2 `--check tex` (Linux microbench only, no iOS needed)

1. Render one frame with the `tex4` pipeline to `target`.
2. Read back: `vkCmdCopyImageToBuffer` into a host-visible buffer. `target` is OPTIMAL.
3. **CPU reference.** Regenerate the same LCG noise. For pixel centre `(px+0.5, py+0.5)`:
   - `uv = ((px+0.5)/W, (py+0.5)/H)`. This is from `fullscreen.vert`: `gl_Position.y = 2·p.y − 1`, so `uv.y = 0` is the
     top row under Vulkan's positive-height viewport (`microbench.c` sets `{0,0,W,H,0,1}`). Also report the flipped-V
     error, so an orientation slip can't pass as "nearest";
   - the four bilinear REPEAT samples at `uv`, `uv+(1.5/1024,0)`, `uv+(0,1.5/1024)`, `uv+(1.5/1024,1.5/1024)`,
     with texel centres at `(i+0.5)/1024`;
   - average them.
4. **Compare** 4096 pixels on a fixed stride, in BGRA order.
   - Tolerance: ≤ 4 LSB. The bilinear weights are quantized, each sample rounds, and A9 unorm8 output goes through f16
     RTZ. If you see off-by-one, check the margin first.
   - Print `MB check tex4 max_err=<lsb> bad=<n>/4096 nearest_err=<lsb>`, where `nearest_err` is the same comparison
     against a NEAREST reference.
   - **PASS:** `max_err ≤ 4 && nearest_err ≥ 32`. `nearest_err` is the real signal.

## 7. Open questions

- **Apple f16 issue rate:** needs `alu_half` on iOS. Until then the 2× is [I] marketing only.
- **`4d04` wait control** after the first sample in `f_tex2v`: unresolved. Don't emit it.
- **Apple's `0x81` FMA header** (Lane B): still unresolved.
- **WebKit on iOS 16** using ANGLE's MSL translator: [I]. A WebKit binary from the device would settle it, but it's
  low value, because the ANGLE source is unambiguous.
- **Merged-subpass state ignored by G5P job init:** latent bug for render-pass objects with input attachments. Out of
  scope here; route it to whoever owns render passes.
