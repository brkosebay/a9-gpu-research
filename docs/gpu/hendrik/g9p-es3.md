# G9P (A10) ES 3.0 enablers: series `g9p-es3`, rungs, pointers (2026-11-03)

Henrik is working towards GLES 3.0 on the A10. This series ports our A9 (G5P) ES 3.0 enablers onto
his published `pvr_*` + `src/imagination/g9p` driver, behind a build option. **Nothing here has run on
an A10.** The local branch is only in `build/third_party/orchard-mesa-g9pes3`, with push disabled; the
owner decides whether to publish. It will land as commits on the draft PR `brkosebay/mesa →
OrchardLinux/mesa`.

## The series (`g9p-es3`, off his `main`)

Option `-Dimagination-g9p-es3` (default off) → `PVR_G9P_ES3`. 10 commits, 1981 insertions, 0 deletions
in his files: every hunk is under `#ifdef PVR_G9P_ES3`, and the new files build only with the option.
Trailers on every commit: `Generated-by: LLM`; `Co-developed-by: Henrik Klee` on the 9 commits that
adapt his code; `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (the `g5p-m1` convention).
The author is the noreply GitHub identity. There are no other addresses.

| Commit | Piece | Where in his tree | A9 hardware | A10 |
|---|---|---|---|---|
| `bf2af271211` | the option | `meson.options`, `src/imagination/meson.build` | n/a | builds |
| `955acdf9e29` | device features/limits for what the G9P paths implement (1/2/4 targets, 1 sample, XFB, depth formats) | `pvr_g9p_es3.[ch]`, `pvr_physical_device.c`, `pvr_formats.c` | n/a | untested |
| `50c71358964` | FS with 2/4 colour outputs (2n output regs, the A9 compiler's layout) | `g9p/g9p_compile.[ch]`, `g9p/g9p_es3_isa.h` | exact (2, 4 targets) | untested |
| `c706441a383` | 2/4-target clear/load/EOT device programs from our encoders, render job words | `pvr_arch_g9p_es3_gfx.h`, `pvr_arch_g9p_gfx.c`, `pvr_device.h`, `pvr_job_render.h` | exact | untested; **differs:** 4 targets set 0xe3 (cluster 1) and 0xfa (0x4070), the A9's 8-register values; the A9 also writes W3c8/W6b0, which the A10 stream doesn't carry |
| `53257c0baf7` | VS stores its own XFB records (32-bit stores, one component each) | `g9p/g9p_compile.[ch]` | exact (2 buffers, 3000 vertices) | untested; check r0 = vertex index *including* firstVertex |
| `2a15a5e29ce` | XFB buffers, counters (resolved at record time), limits | `pvr_arch_g9p_es3_gfx.h`, `pvr_arch_g9p_gfx.c`, `pvr_arch_xfb.c`, `pvr_cmd_buffer.h`, `pvr_pipeline.h` | exact | untested; no XFB queries, no `DrawIndirectByteCount` |
| `7f5c9630cba` | D16, D32F, S8, D32F_S8 attachments and stencil tests (ZLSCTL, separate stencil plane, ISPA/B per face, depth/stencil clears) | `pvr_arch_g9p_es3_gfx.h`, `pvr_arch_g9p_gfx.c`, `pvr_formats.c` | exact (all four) | untested; **differs:** a stencil base breaks the depth load on A10 (his notes), so it's set only with a stencil aspect. The D32F_S8 plane layout is the A9's (upstream Rogue's is F64Z) |
| `06cc2a448b3` | sampling 2D arrays and cubes (cube op `087d`, layer coordinate) | `g9p/g9p_compile.c`, `g9p/g9p_es3_isa.h` | exact (textypes rerun) | untested; `087d` isn't among the ISA forms compared |
| `26cf47cee5c` | 2D array / cube images and views (64 B layer stride, 16 KiB past 16 KiB), NPOT | `pvr_arch_g9p_es3_gfx.h`, `pvr_arch_g9p_gfx.c`, `pvr_image.c` | exact | untested; check the sample word's dimension nibble and the NPOT mip twiddling |
| `5cc7faef9ad` | README: the option, a "check first on A10" table, what isn't built, the 4× MSAA mapping | `g9p/README.md` | n/a | n/a |

**Not built, and different from the brief** (each one stated in the README and in the commit):
- **Depth sampling is not built.** The A10 keeps depth in a layout of its own. This is the one ES 3.0
  term the G9P paths can't honour yet, so Zink won't report ES 3.0 by itself. The rungs use
  `MESA_GLES_VERSION_OVERRIDE=3.0`.
- **No D24S8.** On the A10, X8_D24 crashed the GFX firmware (glmark2). Zink renders `DEPTH24_STENCIL8` as D32F_S8.
- **4× MSAA: no code**, only the mapping in the README. It needs the render target and kernel half on the
  A10 first: dataset ×4, ISP_AA mode 2, ISP_CTL 0x7, sample positions. Then the userspace half: PBE layout 4,
  EOT `1c09`, DOUTU rate 2, ISPCTL upass 7. Until then the option reports one sample.
- No XFB queries, no 3D textures, no cube arrays, no blending with several targets.

## Checks (offline; nothing ran on a device)

- **Gate, option off.** The strict gate (`g9p-es3.sh gate-off`, tip `28d88ce04a7`, the same tree as `b60d7699afc`) is **not**
  byte-identical: 164 of 165 installed files match `main1`. `libvulkan_powervr_mesa.so` is
  `ad264ddd…5335`, against `76e29856…c7584` for main, because of the `__LINE__` constants shifted by the inserted lines. So the
  hook-commit gate applies (`orchard-m1.sh padded` + `linecheck`, the step-1b rule): **PASS**. His main padded with the same
  blank lines (279 lines in 12 files) builds all 165 installed files byte-identical to the series, option
  off (`libvulkan_powervr_mesa.so` `ad264ddd…5335` for both, `gate-a/es3h*.sha256`). `linecheck` against his
  unpadded main: `.rodata`, `.data.rel.ro`, `.data`, `.dynsym`/`.dynstr` and `.eh_frame*` are identical, and
  `.text` is the same size (0x40c4c4). Of the instructions, 35 differ, all `mov`/`movk` immediates into
  w registers (the `__LINE__` constants). The gate ran on `b60d7699afc`. The final tip differs from it
  only in `README.md` and one comment in `pvr_arch_g9p_es3_gfx.h`, which is included only under the option.
- **Option on:** `ninja -j2` build with 0 errors and 0 warnings in the G9P files (`g9p-es3.sh dev-sync`, final
  tip). There's no install hash for the option-on build.
- **Host encoder test** (`scripts/gpu/g9p-es3-host-test.sh`, `tools/g9p-es3/test-mrt-programs.c`): the
  branch's MRT device-program encoders against our A9 generators, PASS 57/0. Private: it reads our
  fork's `g5p_mrt_programs.h` into a temp dir and is never part of the branch.
- **Publish audit** (`scripts/gpu/g9p-es3-audit.sh main`, the four tools of `publish-audit-20261102.md`):
  - `arrays.py` rc 0. Its 24 lines cover whole files. Of those, 19 are in his `main` already
    (`pvr_arch_g9p_gfx.c`, `pvr_formats.c`; the same 19 come back on main's copies). The 5 added ones, all in
    `pvr_arch_g9p_es3_gfx.h`, are PDS data built at run time (BO addresses, `doutd_ctrl()`,
    `usc_offset()`), not literals. The depth/stencil commit adds no hex word literal at all (its words are
    `pvr_csb_pack`/`ROGUE_` fields).
  - `hexscan` 0 dense or long-hex. `privscan` 0 hits on the added lines. gitleaks 0. No e-mail addresses
    in the changed files, and only the noreply ones in the messages.
  - No Apple helper programs or captured words: the ZLS and ISP words are packed from Rogue's csbgen fields,
    with values checked against Apple's A9 driver in our capture (the M6 "keep" case). Commit
    `7f5c9630cba` and its comment now say so explicitly.

## Rungs for the A10: `docs/gpu/hendrik/g9p-es3-rungs/`

Recommended location: a separate probe directory, sent as is (Henrik keeps probes in OrchardLinux/gpu
`tools/a10/`, and Mesa's tests are piglit and dEQP). Not the Mesa branch. Seven programs, GLSL only (the
Makefile generates the SPIR-V headers), 304 KB. Each program checks itself against a CPU reference.
`README.md` there has the build/run steps, the PASS lines, the A9 output and the first checks on an A10:
`mrt/mrt-vk.c`, `xfb/xfb-test.c` (the XFB rungs only; the A9 vertex-PDS `vpds-*` rungs and the `PVR_G5P_*`
hooks were dropped), `depth/depth-vk.c`, `textures/tt-vk.c` (one, arr, arr-layer, cube, npot, npot-lod,
arr-mip), `msaa/msaa-vk.c` (`--expect-no-msaa` is the passing form for now), `gles/es3-smoke.c`
(surfaceless, Zink), `gles/ds-ladder.c` (the `ctl` + `ds_*` rungs of blend-ladder, surfaceless).
Audit: arrays.py 5 small colour/sample-position constants, hexscan/privscan/gitleaks 0. `cc -fsyntax-only`
is clean on the Mac against the Mesa headers. Not built or run on aarch64.
Expected on the A10 with this series: `es3-smoke zs` FAILs (no depth sampling), so run `--only mrt,xfb`. XFB lines
print `query=skipped bytecount=skipped`. Never run on A9 hardware (fake device only): the xfb rungs
`rec, first3, overflow, instanced, resume` and `ds_clear_rect`.

## Pointers to send now (public `brkosebay/a9-gpu`, `main`, pushed 2026-11-02)

The remote blobs equal the local snapshot `build/publish/a9-gpu`:
- `docs/gpu/STATUS.md`: overview (snapshot from 11-02; the workspace copy has moved on)
- `docs/gpu/experiments/mrt.md`: MRT 2/4 (current)
- `docs/gpu/experiments/xfb.md`: transform feedback (11-02; workspace has 91 changed lines since)
- `docs/gpu/experiments/depth-msaa.md`: depth/stencil formats, sampling, 4× MSAA (current)
- `docs/gpu/experiments/es3.md`: Zink ES 3.0 bring-up (11-02; workspace has 201 changed lines since)

**Not public:** `msaa.md`, `textypes.md` (cube/array), `gles3-tex.md`, `gles3-gap.md`. To cite them, the
snapshot needs a refresh through the publish audit first.

## What Henrik must verify on the A10

1. Option-off build equals his own (or run `padded` + `linecheck` as above).
2. In this order, each on an option-on build: 2 targets (no new register values), then 4 targets (0xe3/0xfa,
   and whether the A10 needs the A9's W3c8/W6b0 equivalents); XFB r0 including firstVertex (`first3`
   rung); stencil base vs depth load; the D32F_S8 stencil plane layout; D16 background depth; the
   `087d` cube op and the dimension nibble; layer stride and NPOT twiddling.
3. Depth sampling layout on A10: the missing ES 3.0 term.
4. MSAA: the kernel and render-target half first, then the userspace words in the README.

## Workspace files (untracked; the orchestrator commits)

`docs/gpu/hendrik/g9p-es3.md` (this file), `docs/gpu/hendrik/g9p-es3-rungs/` (33 files),
`scripts/gpu/g9p-es3.sh`, `scripts/gpu/g9p-es3-audit.sh`, `scripts/gpu/g9p-es3-host-test.sh`,
`scripts/gpu/orchard-pad.py` (also used by the `orchard-m1.sh padded` lane), `tools/g9p-es3/test-mrt-programs.c`.
Outputs are in `build/gpu/g9p-es3/` (gitignored). Local branches in the clone: `g9p-es3` (final), plus
`g9p-es3-msg0` and `g9p-es3-msg1` (the same code before the message rewording; can be deleted), and
`m1-padded-es3h` (gate only).
