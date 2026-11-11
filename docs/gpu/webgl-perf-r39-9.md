# R39-9 GPU performance lane: HW WebRender's per-frame CPU copy

Generated-by: LLM. Host-sealed 2026-11-08, device pending. Device runbook: `DEVICE-READY-r39-9.md`.

## Device profile (r39-7.1, `build/gpu/r39-7.1/device-stacks/`)

Symbolized with the unstripped r39-7.1 build. The build ID `77b6721e…` matches
the device library. Tool: `scripts/gpu/orchard/r39-9/rank-stacks.py`. Its
inclusive column is unreliable because perf truncated the call chains, so the
numbers below are self samples plus the driver's own transfer log.

| HW WebRender, 100 fish | share of all samples |
|---|---:|
| `zfq0` (zink flush thread, all inside `vkQueueSubmit`) | 50.7% |
| … `g5p_copy` self | 21.0% |
| … libc `pthread_once` (from `util_format_unpack_description`) | 14.8% |
| … `util_format_b8g8r8a8_unorm_pack_rgba_float` and other util format code | ~12% |
| … zink's own code (libgallium) | 0.1% |

For SW WebRender, `zfq0` is 5.9% and contains almost no `g5p_copy`.

`PVR_G5P_PERF_LOG` shows the cause. After every 1024×1024 WebGL pass (vdm=27568),
HW WebRender runs a single-command transfer of **53–63 ms** CPU. That is about
680 ms of every second at 12 fps, roughly 57 of the ~83 ms per frame. All other
transfers are under 1 ms. In SW WebRender the per-frame copies are 2–3 ms.
The hot pack symbol, plus the unpack symbol (an ICF-folded
`r8g8b8a8_unorm_unpack`), identify the copy as R8G8B8A8_UNORM →
B8G8R8A8_UNORM, 1024×1024. That is the WebGL drawing buffer going into the
compositor texture. The host repro's transfer log confirms the same formats.

## Fix (`752a5e90b7d`, branch `g5p-r39-9-perf`)

Unscaled colour conversions now resolve the formats once per rectangle:
- byte permutation for 4×8-bit UNORM or pure-integer array formats;
- for every other format pair, row chunks go through one util unpack and one util pack call;
- the rectangle's corners are bounds-checked once, and offsets are split into column and row terms.

Depth/stencil, compressed, scaled and padded-twiddle surfaces keep their existing paths.

## Host before → after (ARM64 container, fake node)

| Measurement | r39-7.1 | r39-9 |
|---|---:|---:|
| `g5p_copy` 1024² RGBA8→BGRA8, twiddled→linear | 15.2 ms | 0.88 ms |
| `g5p_copy` 1024² RGBA8→BGRA8, twiddled→twiddled | 17.1 ms | 0.98 ms |
| `g5p_copy` 1024² RGBA16→RGBA8 (row path) | 14.8 ms | 4.5 ms |
| zink frame: 500 draws + RGBA8→BGRA8 present + 4 passes, CPU/frame | 13.3 ms | 2.0 ms (−85%) |
| same frame, transfer max | 12.6 ms | 0.84 ms |
| controls: same-format present / no present, CPU/frame | 1.3 / 1.1 ms | 1.4 / 1.3 ms (noise) |

Correctness:
- 756 ordered format pairs, 24,192 cases bit-identical to r39-7.1's `g5p_copy`, under ASan/UBSan;
- zink upload → blit → readback in both directions, flipped and unflipped: exact on both libraries;
- the real-driver CPU-transfer oracle: 16/16.

## Package r39-9 (light gates)

- `build/gpu/r39-9/package/packages/vulkan-powervr-1:27.0.0_devel.r39-9-aarch64.pkg.tar.xz`,
  sha256 `892cedb0801b…`.
- Packet `build/gpu/r39-9/runner.tar.gz`,
  sha256 `c5edd78aff61…`.
- Gates:
  - step6 15/15 and step7 28/28 ×2;
  - corpus270/default288 identical;
  - numeric host 28/74/15, the same as r39-7.1;
  - zink lifetime/VDM PASS;
  - transaction r39-7.1 → r39-9 → r39-7.1 → r39-9;
  - ABI PASS.

## Next

1. **The copy on the GPU** (owner goal). zink's `blit_native` already falls back to
   `util_blitter` (a textured-quad draw) when the format lacks `BLIT_SRC/DST`.
   The Asahi-style answer is a GPU `vkCmdBlitImage`/copy through `vk_meta` for
   G5P, instead of the CPU transfer queue. Removing the blit bits instead
   would break the Vulkan required-format table, so at most use it as an env A/B.
2. Then use the r39-9 HW stacks (`stacks-hw100-r399`) to rank what remains.
   Candidates: the ~10/s 1536×2048 `load=1` passes, about 400 MB of named
   pre-job cache ranges per job (`reads_known=0` on the WebGL pass), and the
   other zfq0 samples.
