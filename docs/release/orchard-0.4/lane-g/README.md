# Lane G: local G5P kernel topics

Prepared, unpublished. No device access, push, PR mutation, changelog edit or Mesa edit. Read current Orchard CONTRIBUTING.md and AGENTS.md from the fresh checkout. No m1n1 source tree was opened.

## Branches and provenance

Orchard checkout: `build/orchard-0.4/orchard-g`.

| Repository | Base topic | Pipeline topic |
|---|---|---|
| Orchard | `j71t-04/g5p-base`, `7bd2eec` | `j71t-04/g5p-pipeline`, `9a0f4a7` |
| OrchardLinux/linux | `j71t-04/g5p-base`, `022015947217254c59b48319a3521ebb16552e31` | `j71t-04/g5p-pipeline`, `bf6ed1829b96931648ae417e2b02bdda1fbd8705` |

The fresh shallow blobless Linux clone is `/src/orchard-linux-g` in Docker volume `linux-a9-src`. Its fetched main is `564a3550e816642c71a026bb3521509d5e159ca5`. Orchard main is `ce9c61a7662b65213173ee19e0803fa755bad668`. The generated Linux main says its config layer is from Orchard cfc6796. Subsequent Orchard kernel changes listed by `git log cfc6796..ce9c61a -- kernel platforms` concern apple-4k device patches; this lane does not regenerate or claim to refresh that separate generated branch. The apple-16k GPU baseline includes main's A10 changes. Re-export/replay is pinned to these fetched heads, not a promise against later main.

Base source is sealed warmport `d67f133590a`; pipeline carries each of the nine T1→opt1 commits through `78775ea3b9ebd50647653d6e3b115447e5e75f9d`. Only G5P directories/UAPI were projected initially. The build identified one additional dependency: the native GEM uncached-export contract and ADBE callback, now a separate base source commit. No broad source replacement was performed. #74 was read using gh view/diff; its older component projections are superseded by this stack.

The split is practical: seven base source commits (binding; board DT; UAPI; transport; VM/cache; render/compute; PRIME cache contract), then nine pipeline commits. Full commit IDs and subjects: `kernel-commits.txt` (not published), `orchard-commits.txt` (not published). VM/cache precedes its render inclusion sites. These inclusion-file commits are review layers; intermediate source commits are not individually boot-qualified.

Export used current `tools/kernel-tree/export.py`. All G5P driver patches are explicitly in `drivers/drm`, because Orchard applies that directory before `drivers/gpu`; putting transport there would otherwise break later pipeline patch application. Existing upstream patch numbers were retained. Base uses DRM 0008–0013 plus `devices/s8003/0001`; pipeline uses DRM 0014–0022. `export-base.log` (not published) and `export-pipeline.log` (not published) reproduce their topics; `replay.log` (not published) independently applies all 16 patches in actual drivers/devices order and obtains the exact pipeline source tree. One inherited blank-at-EOF whitespace warning remains.

## Behavior and integration

All production controls are immutable at each donor revision's defaults. The final topic fixes joint=1, absolute stamps=1, depth=2, PM-record=1, ordered waits=1 and ahead-on-submit=1. The deleted runtime-idle work retains only the default open-file accounting and inert lifecycle scaffolding; no idle transition is possible. The captured idle-policy coefficient header is omitted entirely. The only module parameters left are job_log and job_time_log (diagnostic only); they were retained rather than redesigned into debugfs during this port.

Intentional differences from opt1: production boot/module overrides are unavailable; disabled idle/PM-touch experiment arms and enable callback are gone; platform-driver registration now uses normal compatible matching rather than checking the root machine and named platform device before registration. The node uses canonical `apple,s8003-gpu` rather than `gpu,s8003`; only J71t enables it. On a machine without that enabled node, registration can succeed without binding. These lifecycle/override differences require exact-device qualification. No intended difference to default GPU job encoding, waits, deadlines, cache policy or memory budgets was introduced. Hardware equivalence is not claimed from the host build.

Main's PowerVR/imagination code for A10 (711ec3e, de8f6a0, 68d5775) is preserved: `a10-main.txt` (not published). Shared DRM changes are only the opt-in native GEM exporter cache query plus ADBE's existing DMA allocation functions with the explicit immutable cache contract. Unknown/imported exporters stay conservative. This dependency is necessary to retain opt1's PRIME cache policy; it affects the shared GEM object function table and ADBE and needs owner regression review. The existing A10 firmware converter, recipe handler and recipes are retained. The G5P converter/recipe comes from #74 and independently pins original firmware size/digest; source and tests contain no firmware bytes. Device/chip TOML adds scope/qualification notes without inventing unsupported GPU feature keys or promoting features to working. Matrix regeneration produced no matrix change.

## Validation and limits

- Full `Image.gz dtbs` build passed on the exact pipeline source SHA above, Clang 22.1.8 in linux-a9-kbuild. Debug info was disabled for this host build to conserve disk. Initial missing-exporter-helper compilation failed and was fixed in the base commit; final success is `build-final.log` (not published). Five inherited unused-expression warnings in the G5P render source remain. No new tests were added; the existing #74 converter tests were carried forward.
- Artifacts: `build/kernel-orchard04-g/{Image.gz,s8003-j71t.dtb,.config,COMMIT,RELEASE}`; hashes in `artifact-sha256.txt` (not published). Release is `7.3.0-rc1-orchard04-g`. Modules/initrd are not packaged by this lane; the orchestrator must build the exact exported release set before flying. These are compile receipts, not a complete boot bundle.
- Both shipping configs resolved with Orchard's existing Debian Clang 19 toolchain image: `configs.log` (not published). The only shipping config diff is `CONFIG_DRM_APPLE_G5P=y` on apple-16k. apple-4k is unchanged and cannot enable the 16-KiB-dependent driver; no second full apple-4k kernel build was performed. The host compile used debug-info-off; the shipping config retains main's debug settings.
- Installed-checkout unit suite: 754 tests, 7 failures, 1 error, 1 skip: `unit-tests-installed.log` (not published). The same failing cases reproduce on a pristine archive of pinned main: `baseline-failures.log` (not published), 8 tests, 7 failures and 1 error. They are the macOS shell/od-dependent root/NFS/Wi-Fi tests, not converter failures. All three G5P extraction tests passed. The first uninstalled run had additional package-metadata/import errors and is retained in unit-tests.log for transparency; it is superseded by the installed run.
- UAPI is unchanged from opt1. `uapi.diff` (not published) is the requested raw comparison with Mesa g5p-opt1's copy; `uapi-summary.txt` (not published) lists source mismatches. Mesa retains removed legacy probe/compute names and a separate typed-compute header. Shared declaration differences are render-target reserved storage vs pm_blocks/pad2/reserved; render-info reserved union vs named fields; V3 flags vs pad. Mesa's SKIP_EMPTY_TILES names/capability are not supplied by this kernel. These source differences predate this export and are not silently “fixed” here: lane M must retain capability gating and synchronize its header copies. A compiled 64-bit ABI comparison including Mesa's supplemental typed-compute header found identical key struct sizes, render/compute ioctl values, WAIT_3D=2 and capability bit 34: `uapi-layout-kernel.txt` (not published), `uapi-layout-mesa.txt` (not published). This verifies those binary layouts, not every semantic use of reserved fields.
- Disk was checked before clone/build; build started above 10 GiB and remained above the threshold. No other lane's trees, caches or processes were removed. No hardware fps/GPU time results are claimed.

## Handoff

Merge base before pipeline, and pair WAIT_3D with lane M. Drafts: `PR-base.md` (not published), `PR-pipeline.md` (not published). Exact device procedure and opt1 workload adaptation: `DEVICE-TESTS.md` (not published), `flight.sh` (not published). J71t cold/warm GPU tests and J71b shared-driver/config regression remain required. Publication and proposed changelog wording belong to the orchestrator/owner.

Retain the two source branches, Orchard checkout, receipts and small compile artifacts for review. The lane-local venv is retained for follow-up tests. The aborted full-history clone was replaced by the shallow clone. The temporary baseline archive and projection helper scratch scripts were moved to `~/.Trash/orchard04-g-scratch-20261110` for reversible cleanup; source build objects are cleaned after recording receipts. Source worktrees under `/src/wt` and all a9/* refs were read only.

## Parameter disposition as implemented

| Control | Final value / disposition |
|---|---|
| boot_alive_settle_us | Fixed 2000 |
| idle_tick_maintenance | Deleted; retain default false behavior |
| idle_fw_policy | Deleted; retain default false behavior |
| idle_low_pstate | Deleted; retain default false behavior |
| render_user_cache_import_wc | Fixed true |
| render_user_cache_read_va | Fixed true |
| render_user_cache_private_wc | Fixed true |
| render_user_cache_receipts | Fixed false |
| autoboot | Fixed true |
| autoboot_wait_s | Fixed 120 |
| render_user_event_wake | Fixed 2000 |
| render_user_post_event_us | Fixed 50 |
| render_user_sync_range | Fixed 3 |
| render_pinned_mib | Fixed 1024 |
| render_user_ordered_waits | Fixed true |
| render_user_abs_stamps | Fixed true |
| render_user_pipeline_depth | Fixed 2 |
| render_user_pm_record | Fixed true |
| render_user_ahead_on_submit | Fixed true |
| render_user_joint | Fixed true |
| render_user_touch_live_pm | Deleted; retain default false behavior |
| render_user_fw_ready_mode | Fixed 2 |
| runtime_idle | Deleted; retain default false behavior |
| render_user_wait_ms | Fixed 20000 |
| render_user_hard_ms | Fixed 60000 |
| render_user_soft_ms | Fixed 45000 |
| render_user_obs_ms | Fixed 2000 |
| enable | Deleted; normal compatible-selected platform probe |
| job_log | Retained diagnostic uint parameter; default 0 |
| job_time_log | Retained diagnostic bool parameter; default false |
