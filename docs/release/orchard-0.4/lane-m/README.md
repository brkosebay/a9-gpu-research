# Mesa lane M — local preparation

Current main: `9b6c177a64905860da62479fced6115d4fa6b50c`. Measured source: `g5p-opt1=8ed61e7cc055e079a0b0592f8284eb772a1ef55b`. Prepared head: `ced43e7db3d7a210e4b9c005ec73b427c1bed540`. Worktree: `build/third_party/mesa-04`. Existing source branches/worktrees were not checked out or edited. Fetching main updated origin/main as requested. Nothing pushed, no PR writes, no device access.

## Stage ledger

| Stage | Branch | Base | Commits / head | Replaces | Build |
|---|---|---|---|---|---|
| foundation | `g5p-04/foundation` | `9b6c177a6490` | 8 / `159b53c0fce1` | #2 | aarch64 ICD PASS |
| pipelines | `g5p-04/pipelines` | `159b53c0fce1` | 5 / `cc52372a00f2` | #3 | aarch64 ICD PASS |
| textures | `g5p-04/textures` | `cc52372a00f2` | 8 / `e4b0a7b0fc2b` | #4 | aarch64 ICD PASS |
| desktop | `g5p-04/desktop` | `e4b0a7b0fc2b` | 45 / `a40d85c3cd11` | #6 | aarch64 ICD PASS |
| compute-memory | `g5p-04/compute-memory` | `a40d85c3cd11` | 35 / `0d40373a3da0` | post-#6 | aarch64 ICD PASS |
| shader-prerequisites | `g5p-04/shader-prerequisites` | `0d40373a3da0` | 85 / `49dd6296d568` | post-#6 | aarch64 ICD PASS |
| queries | `g5p-04/queries` | `49dd6296d568` | 7 / `33ca4a4f67be` | post-#6 | aarch64 ICD PASS |
| shader-format | `g5p-04/shader-format` | `33ca4a4f67be` | 48 / `d02b4e8dcefc` | post-#6 | aarch64 ICD PASS |
| webrender | `g5p-04/webrender` | `d02b4e8dcefc` | 19 / `5885c78cd42d` | post-#6 | aarch64 ICD PASS |
| transfers | `g5p-04/transfers` | `5885c78cd42d` | 12 / `b8e1b3cb45db` | post-#6 | aarch64 ICD PASS |
| sync-performance | `g5p-04/sync-performance` | `b8e1b3cb45db` | 10 / `992e09388118` | post-#6 | aarch64 ICD PASS |
| allocation | `g5p-04/allocation` | `992e09388118` | 3 / `051606cc609a` | post-#6 | aarch64 ICD PASS |
| zink-failure | `g5p-04/zink-failure` | `051606cc609a` | 1 / `63a2a7e2d25e` | shared correctness | aarch64 ICD PASS |
| shared-format | `g5p-04/shared-format` | `63a2a7e2d25e` | 2 / `3ef0dd3dcf9d` | shared correctness | aarch64 ICD PASS |
| g5p-policy | `g5p-04/g5p-policy` | `3ef0dd3dcf9d` | 7 / `ced43e7db3d7` | G5P release defaults | aarch64 ICD PASS |

The post-#6 history contains cross-topic dependencies. This preparation retains chronological prerequisites rather than claiming its commits are independent topic patches: allocation/transfer prerequisites precede compute and queries; shader prerequisites precede queries; sync prerequisites precede final allocation. Generic batch-failure and format fixes have distinct branches/commits. `commits.tsv` (not published) gives every commit, base and preserved author. Source tests carried from opt1 were retained; no new tests were introduced.

Precise-sync gating and preservation of the main G9P signal path are included in the sync stage. Staging/trim/transcode defaults are gated within their introducing policy stage. The partition retains interleaved prerequisites, as identified above; it does not pretend those changes were historically independent. All descriptions are drafts. No device equivalence result is claimed.

## Gating

| Behavior | Detection/default | A/B override |
|---|---|---|
| Zink precise sync | Vulkan `VK_DRIVER_ID_IMAGINATION_OPEN_SOURCE_MESA` AND exact `driverName="Mesa PowerVR G5P"`; default true only there | `ZINK_PRECISE_SYNC` |
| Dead staging flush | same identity; default memory/32 clamped 16–256 MiB only on G5P, zero elsewhere | `ZINK_STAGING_FLUSH_MIB` (0 disables) |
| Idle allocator trim | same identity; 1000 ms on G5P, zero elsewhere | `ZINK_TRIM_MS` (0 disables) |
| S3TC→ETC2 | `DRI_CONF_TRANSCODE_S3TC(0)` globally; detected G5P passes device name `g5p` to Zink driconf; shipped per-device entry selects 1 | driconf/environment `transcode_s3tc=0/1/2` retains original semantics |
| Packed-float ES FBO qualification | new opt-in pipe capability set by Zink only on detected G5P; other screens retain main | normal extension advertisement |
| Empty-else liveness numbering | A9 compute `out->a9`; original G9P increment order retained otherwise | original opt1 behavior on A9 |
| Queue signal scopes | G5P signal implementation only for `apple_g5p`; original main function used otherwise | existing G5P sync switches |

Driver name is set from PowerVR `apple_g5p` device feature, rather than a user-overridable deviceName. GL's G5P option may remain false, as in tex1: detection is at Vulkan runtime. Vulkan feature query precedes Zink driconf parsing. User/app driconf overrides still supersede shipped defaults. Copy/install `00-mesa-defaults.conf` with the private GL package; a library-only deployment loses the S3TC default.

## Builds and option-off comparison

Build runner: `scripts/gpu/orchard04-mesa-build.py`, adapted from `build/tex1/build.py`: same aarch64 container `linux-a9-r39-6b`, ICD setup option array, GL introspection conversion, `-j6`, no debug info. All lane source/build/stage paths in the container are new `/orchard04/*`. Host receipts and libraries are under `build/orchard-0.4/mesa-out/`. Existing `/port-submit` and `/f5b-*` are only read for options, never modified. Each invocation checks host free space against 10 GiB. Initial disk: 14 GiB; later space was freed externally, not by this lane.

Final checks and exact artifact hashes are recorded below after completion. The option-off check builds both final and current main with identical ICD options apart from main not defining the experimental option. Build success alone is not A10 runtime evidence; the orchestrator must do the A10 smoke in DEVICE-TESTS.md.

## Difference from opt1

See `DIFF-TO-OPT1.md` (not published) for each remaining hunk and upstream/port rationale; raw requested diff: `build/orchard-0.4/mesa-out/diff-to-opt1.patch`. Pure G5P backend (`src/imagination/g5p`) and typed winsys (`src/imagination/vulkan/winsys/apple_g5p`) are byte-identical to opt1. Shared A9 compiler hooks were re-ported onto main's compiler, including its new call signature and separate A9 intrinsic dispatch before G9P's handlers. Main's compiler transformations are retained, so exact shader behavior still needs the flight. The nine content-conflict files retain main G9P logic plus A9 hooks. Auto-merged files also need review and hardware qualification; no textual merge is treated as a device result.

## UAPI coordination

`src/imagination/vulkan/winsys/apple_g5p/apple_g5p_drm.h` is identical to opt1, Git blob `5258ade200111217e15497cf3b33624731543450`, SHA256 `185125aed0a8…`. The entire typed winsys directory has zero diff to opt1. Lane G must compare its exported `include/uapi/drm/apple_g5p_drm.h` against this exact copy before the flight.

## Final receipts

All 15 stage ICD builds PASS at the heads in the ledger. Final ICD, private GL install (Zink/EGL/GBM/GLES), and G5P-off ICD PASS at `ced43e7db3d7a210e4b9c005ec73b427c1bed540`. Current-main option-off ICD also PASS. No hardware flight or performance claim.

Build option values match the saved tex1 introspection: [('icd', {}), ('gl', {})].

See `OPTION-OFF.md` (not published) for byte-identical G9P compiler archives and the shared-path review. All existing trailers/authors were retained; the one original F5b commit with no AI trailer had `Generated-by: LLM` added. Every prepared commit now has an AI disclosure trailer.

| Artifact (relative to workspace) | SHA256 |
|---|---|
| `build/orchard-0.4/mesa-out/g5p-policy/libvulkan_powervr_mesa.so` | `be293a178bc6…` |
| `build/orchard-0.4/mesa-out/final/gl-stage.tar.gz` | `55e9fc92d653…` |
| `build/orchard-0.4/mesa-out/final/libgallium-27.0.0-devel.so` | `75fb2c34f407…` |
| `build/orchard-0.4/mesa-out/final/libEGL_mesa.so.0.0.0` | `c9a9e36cfb8a…` |
| `build/orchard-0.4/mesa-out/final/libgbm.so.1.0.0` | `59286ef83ea1…` |
| `build/orchard-0.4/mesa-out/final/libpowervr_g9p.a` | `e8b1ed999e7b…` |
| `build/orchard-0.4/mesa-out/main-off/libpowervr_g9p.a` | `e8b1ed999e7b…` |

The final ICD and GL install are from the same commit. Use the **g5p-policy ICD**, not `final/libvulkan_powervr_mesa.so` (which is the option-off comparison library). Store the GL archive under the flight stack as described in DEVICE-TESTS.md.

## Orchestrator follow-up (2026-11-10)

- Lane D found `g9p_replay` (not installed) failing to link with the G5P option on: `g9p_a9_alu.h` calls
  `g5p_usc_fma_f32_literals()` but `g9p_replay` linked only `libpowervr_g9p`. Fixed on top of `g5p-04/g5p-policy`:
  `2ae828f7f14` "imagination: link the A9 encoders into g9p_replay when G5P is enabled" (g5p configured before g9p;
  `libpowervr_g5p` added to g9p_replay's link when the option is on; option off unchanged). ICD and `g9p_replay`
  build PASS (`build/orchard-0.4/mesa-out/replay-fix/`). Before publication, fold it into the stage that first makes
  g9p call the A9 encoder, or publish it as the first commit of the following stage.
- A full default `ninja` in the ICD configuration stops in panfrost's Rust `kraid` (bindgen type mismatch in this
  container's toolchain, `src/panfrost/compiler/kraid/decode.rs`); unrelated to imagination or G5P.
- The new head for the GL package pin and the flight is `2ae828f7f14` (driver code identical to `ced43e7db3d7`).
