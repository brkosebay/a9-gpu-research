# tex1: S3TC stored as ETC2, and what the A9 samples (2026-11-10)

Follows `mem1-gpu-memory-20261109.md` ("Result: device flight": STK's GPU memory is S3TC decompressed to RGBA8) and
`fable-open-questions-20261109.md` §1 (F1.2, F1.3).
Branch `g5p-tex1` = 3 commits on `g5p-mem1` (worktree `build/third_party/mesa-g5p-port-submit`), head `8ed61e7cc05`.
Package `build/tex1/`, commands `build/tex1/DEVICE-COMMANDS.txt`. No kernel change, no Vulkan-driver change.
**Nothing here ran on the device.**

Grades: [V] read in source or binary, [T] tested here (build container: encoder against Mesa's decoders; GL through
Zink on lavapipe), [D] device data from earlier flights, [I] inferred, [M] to measure on the device.

## 0. In one screen

- **The A9 samples ETC2/EAC, ASTC LDR (all 14 block sizes) and PVRTC; it has no BC.** Apple's own per-format table
  says so (§1). Our driver advertises ETC2/EAC, device-proven; ASTC and PVRTC are not exposed.
- **So the ≤ 8 bpp target for S3TC is ETC2, and it needed no driver work.** tex1 is in mesa/st: an S3TC upload is
  re-encoded to the ETC2 format of the same size (DXT1 → 4 bpp, DXT3/DXT5 → 8 bpp) instead of decompressed to
  RGBA8 (32 bpp). New: a fast ETC2 encoder in `src/util/format`. Switch: `transcode_s3tc=0` (environment).
- **It is lossy:** on 46 STK textures, 37.1 dB against the DXT5 decode, and 1.0 dB further from the original than
  DXT5 itself is (30.7 against 31.7 dB). Worst are normal maps (30–34 dB). No lossless S3TC → ETC mapping exists
  (§4); a near-lossless one exists to **ASTC 4×4** and is the next step (§7.1).
- **Expected:** the S3TC part of STK's images falls to 1/4. `image_kib` at 256: 321 MiB → 100–160 MiB; at 512 the
  5176 allocation failures go away. The split between S3TC and render targets is what the flight measures (§5).
- **Cost:** CPU at upload. Host 36 Mpix/s per core; A9 ≈ 5–6 Mpix/s per core [I], both cores used when free. STK
  at 256: ≈ 5–14 s more loading (two cores – one); at 512: ≈ 20–40 s [I]. The smoke test's `load` line measures the
  rate [M].

## 1. What the A9 samples

### 1.1 Apple's side [V binary]

The format never reaches the kernel: AGXMetalA9 (userspace) builds the texture state, so the evidence is in the
dylib (`build/gpu-userspace/dylibs/AGXMetalA9`, iOS 16.7.10 shared cache), not the kernelcache.

- `AGX::G5::TextureFormatTable::chooseTextureFormatOBJC(MTLPixelFormat)` at **0x207dc25b4** is a jump table
  (u16 entries at 0x207dddd0c, 589 formats) to one static row per format (`texFormat*`, 0x60 bytes,
  `ds-isa-state.md` §2.3). Row `+0x00` is the hardware format code (texture state bits 5–14), `+0x08` the type
  (1 = snorm → code | 0x80, 4 = float), `+0x54` the gamma (3 = sRGB → q1 bit 45), `+0x58` the bytes per texel or
  block (in this dylib; `ds-isa-state.md` §2.3 has the last two 4 bytes higher).
  An unsupported format returns the row `Unsupported` at 0x207de34d8.
- New tool: `scripts/gpu/agx-texformat-table.py [--metal|--all|--raw]` prints the rows and resolves every
  compressed MTLPixelFormat through that jump table.

| Metal format | row (address) | code | A9 |
|---|---|---:|---|
| BC1–BC7 (130–152) | `Unsupported` 0x207de34d8 | — | **no** |
| PVRTC 2 bpp RGB/RGBA (+sRGB) | `PVRTC2RGB` 0x207de1a30 … | 0x50 | yes |
| PVRTC 4 bpp RGB/RGBA (+sRGB) | `PVRTC4RGB` 0x207de1a90 … | 0x51 | yes |
| ETC2 RGB8 / RGB8A1 / EAC RGBA8 (+sRGB) | 0x207de0e30 / 0ef0 / 0e90 | 0x58 / 0x5a / 0x59 | yes |
| EAC R11 / RG11 (snorm: type 1) | 0x207de1070 / 1130 | 0x5b / 0x5c | yes |
| ASTC LDR 4×4, 5×4, 5×5, 6×5, 6×6 | `ASTC4x4RGBA_LP` 0x207ddf990 … | 0x60 – 0x64 | yes |
| ASTC LDR 8×5, 8×6, 8×8 | 0x207ddfbd0 … | 0x65 – 0x67 | yes |
| ASTC LDR 10×5, 10×6, 10×8, 10×10, 12×10, 12×12 | 0x207ddfcf0 … | 0x68 – 0x6d | yes |
| ASTC sRGB, the same 14 sizes | `ASTC4x4sRGBA_UNORM` 0x207ddee50 … | same, gamma 3 | yes |
| ASTC 4×2 / 8×4 (Apple-internal enum gaps) | 0x207ddf930 / 0x207ddfb70 | 0x6e / 0x6f | (not Vulkan formats) |

- `-[AGXA9FamilyDevice isASTCPixelFormatsSupported]` at 0x207ccb5ec returns 1.
- The ASTC HDR rows (222–236) exist with type 4 (float); HDR ASTC is not an A9 feature in Metal. Not pursued.
- Cross-check of the method: the table gives ETC2 0x58/0x59/0x5a, EAC 0x5b/0x5c and ASTC 4×4 0x60, exactly the
  codes the iOS captures showed (`gles3-tex.md` §1.1, `textypes.md` §2).
- PVRTC sRGB rows carry gamma 4, not 3: a different sRGB path than q1 bit 45. Not decoded.

### 1.2 Our driver [V] and the device [D]

| | State | Evidence |
|---|---|---|
| ETC2 RGB8 / RGB8A1 / RGBA8, +sRGB; EAC R11/RG11 ±snorm | advertised, `textureCompressionETC2 = true` | `pvr_physical_device.c:273`; rows `pvr_g5p_format_table.h:193-202` (evidence class G5P1B: formats hardware test, every pixel exact, 2026-11-04) |
| the same through GL (Zink) | native | Zink reports a format from the driver's optimal-tiling features (`zink_screen.c:1564`), so `st->has_etc2` is true; dEQP-GLES3 `texture.format.compressed.*` 44/44 Pass, 2D and cube, POT and NPOT (`build/gpu/cts-banked-r39-20261107/default/gles3.csv`) |
| ETC2 in 2D arrays | allowed (only 3D is refused, `pvr_g5p_formats.c:81`) | not covered by a device test: the tex1 smoke has it [M] |
| ASTC | `textureCompressionASTC_LDR = false`, no rows | 4×4 sampled on the device by the old ICD, a void-extent block only, ±1 (`textypes.md` T3). Other sizes: codes known since today, never run |
| PVRTC | none | never run; no Vulkan core format (only `VK_IMG_format_pvrtc`), no content on Linux |
| BC | `textureCompressionBC = false` | the hardware has none |

## 2. What tex1 implements

Three commits; all in Mesa's shared code, no Zink change, no driver check.

| Commit | Change |
|---|---|
| `49e154a5bdb` mesa/st | glCopyTexSubImage's software path wrote the image's compressed blocks straight into the resource, whose format is another one for a fallback format. It now goes through `st_MapTextureImage()` like every other software path (`st_cb_texture.c:2960`). A fix on its own; with an ETC2 resource the blit path cannot be taken, so it is needed. |
| `6632e88a66b` util/format | `u_format_etc2_enc.c` (884 lines): `util_format_etc2_encode_rgba8()` for ETC2 RGB8, RGB8A1, RGBA8, ±sRGB. |
| `8ed61e7cc05` mesa/st | the transcode and its option. |

**Format choice** (`st_format.c:135`): DXT1 RGB → ETC2 RGB8; DXT1 RGBA → ETC2 RGB8 punchthrough-alpha (a DXT1 hole
and an ETC2 hole both read 0,0,0,0); DXT3 and DXT5 → ETC2 RGBA8 (EAC alpha); sRGB → sRGB. Same block size and
bytes as the source in every case.

**When** (`st_context.c:481`, `:634`): the option is on, the driver has no S3TC, and it samples all six ETC2
formats in 2D, cube, 2D-array (and cube-array, if it has them) textures. Otherwise the RGBA8 fallback as before.

**Upload** (`st_cb_texture.c:705-790`, `:866`): on unmap, the changed rows of blocks are decoded with Mesa's S3TC
decoder and encoded, 4 rows of texels at a time. An image of 128×128 or more is split over the CPUs (≤ 4 threads):
the rows of blocks are independent.

**What stays as it was:**
- The image keeps its copy of the S3TC data, as every fallback format does. glGetCompressedTexImage returns the
  uploaded bytes; glCopyImageSubData, glGenerateMipmap, glTexImage2D of RGBA data into an S3TC format and
  glGetTexImage work through that copy or by sampling the ETC2. [T, §6]
- `GL_EXT_texture_compression_s3tc` is advertised exactly as before; nothing new is advertised.
- Vulkan: nothing changes. An application using our ICD directly sees no BC and has ETC2, as before.

**Switch:** driconf option `transcode_s3tc`, also an environment variable of that name (`driconf.h:316`):
`1` default; `0` the RGBA8 fallback; `2` transcode on a driver that has S3TC too (how it is tested on lavapipe).
`MESA_LOG_LEVEL=info` prints once which path a context took.

**The encoder**, per 4×4 block (searches go over the block's distinct colours: an S3TC block has ≤ 4):
1. ETC1 modes: the split (left/right or top/bottom) that leaves less colour spread in its halves, and the other
   one when it is within 1.5× (`etc1_pick_flip`, `:669`); per half the mean as base colour and the best of the 8
   modifier tables (`etc1_fit_half`, `:192`, exact pruning); RGB444+444 when the halves are too far apart for
   RGB555+333.
2. Planar when that leaves an error (`etc2_try_planar`, `:370`): least-squares plane, RGB676.
3. T and H when that still leaves an error (`etc2_try_th`, `:484`): the block as two colour clusters.
   **This is what S3TC content needs:** an S3TC block is two endpoint colours of any hue plus two mixes; an ETC1
   half is one colour plus offsets along grey. Without T/H: 33.8 dB; with: 37.1 dB.
4. Alpha (`eac_encode_alpha`, `:750`): all 16 EAC tables × the multipliers that fit the block's range; a constant
   block is exact.

## 3. Why not something else

- **Expose BC:** the hardware has none (§1.1).
- **ASTC as the target:** 8 bpp at 4×4, so DXT1 would double. For DXT5 it is the better target and the next step
  (§7.1), but real ASTC blocks have never run on the A9 through our stack, and it needs driver rows. ETC2 is
  proven today.
- **PVRTC:** needs square power-of-two textures and has no Vulkan core format.
- **Hide S3TC from GL:** STK then uploads RGBA8 itself (`sp_texture.cpp:282-315`): the same 32 bpp.

## 4. Quality [T]

Measured by `scripts/gpu/tex1/run-check.sh` (`etc2-check.c`): 47 textures from STK's asset repository (every 14th of
`https://svn.code.sf.net/p/supertuxkart/code/stk-assets/textures/`, list in `scripts/gpu/tex1/stk-sample.txt`;
`prep-images.py` makes the input files), reduced to ≤ 512 as STK does, compressed with
Mesa's DXT encoder, then transcoded. "DXT decode" is what the RGBA8 fallback shows today. Logs:
`build/tex1/host-tests/etc2-check-stk.log`.

| Source → target | ETC2 vs DXT decode | DXT vs original | ETC2 vs original | alpha, ETC2 vs DXT |
|---|---:|---:|---:|---:|
| DXT1 → ETC2 RGB8 (4 bpp) | 37.0 dB | 31.8 | 30.7 | — |
| DXT1 RGBA → ETC2 RGB8A1 (4 bpp) | 36.7 dB | 32.6 | 31.3 | exact (0 flips) |
| DXT5 → ETC2 RGBA8 (8 bpp) | 37.1 dB | 31.7 | 30.7 | 55.1 dB |

- Per texture (DXT5, 43 textures that DXT does not reproduce exactly): min 30.2, 10th percentile 34.4, **median
  38.4**, 90th 46.0 dB. Loss against the original on top of DXT's: median 1.5 dB, worst 4.7 dB.
- Worst: `gfx_kartDirt_a_Normal` 30.2, `stklama_gravelRoad_a` 30.3, `tapis` 30.7, `stktex_snowRock_a_Normal` 33.7.
  **Normal maps are the weak case** (two independent channels; ETC varies along grey).
- Block modes chosen (DXT5): differential 40 %, planar 41 %, H 12 %, T 5 %, individual 2 %.
- Alpha where it varies (13 textures): min 41.5, median 52.5 dB.

**Is there a lossless path?** Not to ETC. A DXT colour block is 4 colours on a line of any direction in RGB; an
ETC1 half is one colour plus the same offset on all three channels. Only a DXT block whose two endpoints differ
along grey maps without loss. T/H give two free colours but in RGB444. To **ASTC 4×4** an opaque DXT block maps
almost exactly (§7.1).

## 5. Expected on the device [M]

- **Smoke (200 DXT5 textures of 256² + mips):** `image_kib` 17 000–19 500 with tex1, 68 000–70 500 with
  `transcode_s3tc=0`.
- **STK.** `image_kib` = (RGBA8 bytes of S3TC textures) / 4 + everything that is not S3TC (render targets, shadow
  maps, GUI, fonts). mem1's flight gave only the sum, so the saving is a range:

| | mem1 [D] | tex1 [I] |
|---|---:|---:|
| 256: `image_kib` | 320 931 | 100 000 – 160 000 |
| 256: STK pinned | 612 MiB | 390 – 450 MiB |
| 512: `image_kib` | 584 383 (cut off by the 768 MiB VM limit) | 250 000 – 330 000 |
| 512: `alloc_fail` | 5176 | **0** |

  The run also yields the split: S3TC share (as RGBA8) = (mem1 `image_kib` − tex1 `image_kib`) × 4/3. If the
  saving at 256 is under ~100 MiB, render targets are the larger part and the next lane is those, not textures.
- **Staging:** an upload's staging buffer is the level's size, so it is 1/4 too (`buffer_kib`).
- **Not changed: the CPU copy.** Mesa keeps the S3TC data of every fallback texture in malloc memory (R2 of the
  earlier report): 1/4 of the RGBA8 bytes, ≈ 55–75 MiB at 256 and ≈ 150–210 MiB at 512 [I]. After tex1 it is as
  large as the GPU copy. §7.2.
- **Upload CPU:** host (M4 Pro) 36 Mpix/s per core for DXT5, 42 for DXT1 (encoder alone, `etc2-check`). A9 ≈ 5–6
  Mpix/s per core [I] (single-core ratio ≈ 1/7), 2 cores. STK's S3TC texels: ≈ 56–77 Mpix at 256, ≈ 217 Mpix at
  512 if its set is 830 MiB of RGBA8.

## 6. What was and was not tested

- [T] **Encoder against Mesa's decoders** (`texcompress_etc.c`, the object of the GL build): on 46 STK textures × 3
  formats and synthetic images for every mode (holes, partial blocks, 2×2 and 1×1 levels), the decoded blocks have
  **exactly** the squared error the encoder chose them for. All five colour modes and punchthrough T/H occur.
- [T] **GL, Zink on lavapipe, `transcode_s3tc=2`** (`scripts/gpu/tex1/run-smoke-host.sh`, logs in
  `build/tex1/host-tests/`):
  - `tex1-s3tc-smoke` PASS: 8 formats × 7 mip levels + sub-image update, DXT5 and DXT1-sRGBA in a 2D array and a
    cube map: 32–36 dB colour, 43–47 dB alpha, 0 alpha flips. Without the option: every row exact (the test's own
    S3TC decoder equals the native path).
  - `tex1-s3tc-paths` PASS (desktop GL 4.6): glGetCompressedTexImage returns the upload byte for byte;
    glGetTexImage, glTexStorage2D + sub-images, pixel unpack buffer, glTexImage2D of RGBA data, glGenerateMipmap,
    glCopyTexSubImage2D, glCopyImageSubData.
- [T] ICD and GL stack build as mem1 did (same container, build dirs, options; `build/tex1/build.py`).
- **Not run anywhere:**
  - the path on the A9 (first flight = commands step 2);
  - the RGBA8 fallback after the CopyTexSubImage change (lavapipe has S3TC; `transcode_s3tc=0` on the device
    exercises the fallback's upload path, not that call);
  - ETC2 2D arrays on the A9.

## 7. Next (ranked)

1. **ASTC 4×4 as the target for DXT3/DXT5 (near-lossless and ~10× cheaper to encode).**
   - An opaque DXT block is two RGB565 endpoints and 2-bit indices. ASTC 4×4, one partition, LDR RGB direct
     endpoints, 2-bit weights: 11 + 2 + 4 header bits + 32 weight bits leave 79 bits for 6 endpoint values, so
     they are stored at 8 bits: **the endpoints are exact** and the weights 21/64 and 43/64 are within 1.3/255 of
     DXT's 1/3 and 2/3. No search: bit packing only.
   - With varying alpha (dual plane): endpoints at 48 levels (≤ ±2.7), alpha at 4 weights instead of DXT5's 8.
     Mildly lossy, only in those blocks.
   - Needs (a) ASTC 4×4 UNORM/sRGB rows in `pvr_g5p_format_table.h` (code 0x60, selectors RGBA; captured and
     §1.1), without BLIT_SRC (the CPU blit has no ASTC decoder) and advertised per format, not through
     `textureCompressionASTC_LDR`; (b) **one device rung with real blocks**: only a void-extent block has run.
   - DXT1 stays on ETC2 (4 bpp).
2. **Drop the CPU copy of transcoded textures (−55 to −210 MiB of malloc for STK).** Keep it only until the
   upload; rebuild it on a read (glGetCompressedTexImage, copies) by decoding the stored blocks and re-encoding
   S3TC. That read-back is then not bit-exact, so it must be an option: owner's call.
3. **Encoder speed, if the device number is too slow:** NEON for the planar and split sums; or a disk cache of
   transcoded blocks keyed by content hash, next to the shader cache.
4. **Full ASTC LDR (`textureCompressionASTC_LDR`, native ASTC content).** Codes for all 14 sizes are in §1.1.
   Open: the memory layout of non-4×4 block grids, and real-block decode.
   - Ghidra first: AGXMetalA9's texture layout code (`build/gpu-userspace/ghidra/agxmetala9.gpr`; row word
     `+0x38` is 2 for every 4×4-block format, 7 for PVRTC 2 bpp, 8 for ASTC 8×5, 0x10 for 12×12: a layout class).
   - **If that does not settle it, the iOS probe** (one scene `g3b-astc` in the capture set of
     `ios-capture-bundle.md`, next to `g3b-compressed`): textures of 24×20 texels, one mip level, in
     ASTC 5×5, 6×6, 8×5, 8×8, 12×12 LDR and PVRTC_RGBA_4BPP at 32×32, **every block a void-extent block whose
     colour is its block index** (R = column × 8, G = row × 8, B = 128); each drawn 1:1 with nearest filtering
     into a BGRA8 target and read back. Wanted: the image-state words (confirms the codes), and the read-back
     (with the same bytes on our side it gives the block order in memory). Plus one 16×16 ASTC 4×4 texture of
     real blocks (any astcenc output) with its read-back, as the reference for 7.1's rung.
5. **PVRTC:** nothing to do. No Linux content; only if a port of iOS assets ever needs it.

## 8. Risks

- **Looks.** 37 dB is visible on close inspection: 4×4 steps on smooth colour gradients, fringes where two hues
  meet, noise in lighting on normal-mapped surfaces. Step 4 of the commands is an eyes-on run. `transcode_s3tc=0`
  is the way back, per process.
- **Loading time.** The transcode is the new CPU cost of an upload (§5). Loading screens get longer; frames
  that upload S3TC while rendering (streaming) would stutter. STK loads up front.
- **Threads.** An upload of ≥ 128×128 starts up to 3 short-lived threads. If STK's own loader threads keep both
  cores busy the gain is small; nothing breaks.
- **All-or-nothing check.** If Zink does not report one of the six ETC2 formats for 2D, cube and 2D array, the
  transcode stays off for the whole context (the info line says so). Expected to pass [V], not run.
- **Mesa change outside our driver.** The option's default is on for every gallium driver with ETC2 and no S3TC.
  Right for this fork; for upstream it would be a per-driver default. Two of the three commits touch files the
  "no Zink modifications" rule does not cover (mesa/st, util).
- **Read-backs of render-to-texture are unaffected**; only S3TC internal formats take the path.

## 9. Files

- Mesa: `src/util/format/u_format_etc2_enc.{c,h}`, `src/mesa/state_tracker/st_{context.c,context.h,format.c,cb_texture.c}`,
  `src/util/driconf.h`, `src/gallium/{auxiliary/pipe-loader/driinfo_gallium.h,auxiliary/util/u_driconf.c,include/frontend/api.h}`.
- Workspace (uncommitted): `scripts/gpu/agx-texformat-table.py`; `scripts/gpu/tex1/` (`etc2-check.c`,
  `run-check.sh`, `prep-images.py`, `stk-sample.txt`, `tex1-s3tc.h`, `tex1-s3tc-smoke.c`, `tex1-s3tc-paths.c`,
  `run-smoke-host.sh`); `build/tex1/` (`build.py`, `package.py`, `DEVICE-COMMANDS.txt`, `host-tests/`).

## Result: device flight (orchestrator, 2026-11-10 ≈00:30 UTC)

Kernel f5d. Log: `build/gpu/tex1-flight-20261110.host.log`. No GPU fault or recovery.

- **Smoke PASS on the A9:** 200 DXT5 256² + mips, `path=transcode`, 0 failures. Images take 8.9 MiB vs 55.5 MiB with
  the RGBA8 fallback. Upload runs at 10.7 Mpix/s transcoded vs 15.5 exact.
- **STK, 60 s, HD textures off, same boot:**

| | mem1 256 | tex1 256 | tex1 256, transcode off | mem1 512 | tex1 512 |
|---|---:|---:|---:|---:|---:|
| image KiB | 320931 | **139810** | 320931 | 584383 | **324269** |
| data live KiB (pinned app data) | 540336 | **278192** | 540336 | 745136 | **556720** |
| kernel BOs | 74 | 42 | 74 | 99 | 76 |
| alloc_fail | 0 | 0 | 0 | **5174** | **0** |
| Shmem at t=45 | 666 MB | **371 MB** | 666 MB | 824 MB | 659 MB |
| MemAvailable at t=45 | 360 MB | **477 MB** | 312 MB | 274 MB | 290 MB |

- **−262 MiB pinned at 256 (−48 %), and the 512 allocation failures are gone.** Images drop 2.3× at 256 and 1.8× at
  512. Part of the image total is render targets and RGBA content, which the transcode does not touch.
- AnonPages rises (283 → 454 MB at 256): Mesa's malloc'd S3TC copies (report §5). That is the next RAM item:
  drop the CPU-side copy after upload.
- STK still does not reach the race in 60 s; a full-length run with fps is still to do.
