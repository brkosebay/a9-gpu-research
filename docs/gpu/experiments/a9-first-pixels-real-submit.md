# a9-first-pixels as a real TYPED_V3 device submitter: done offline, artifact contract

2026-10-30. Claude Sonnet 5.5, implementation sub-agent (userspace lane). **Offline only: no device access, no kernel edit, no r97/prod98/kernel-patch edit, no kernel build slot taken (one `alpine:3.22` container for the aarch64 compile, nothing else), no commit (orchestrator-only).** Nothing here claims device success: the fake kernel paints chosen bytes and proves marshalling, refusal and ordering, not the GPU. No build/test/docker process of this lane is running.

## 0. State

**Finished and run (host, ASan+UBSan, `-Wall -Wextra -Werror -Wshadow`; then aarch64 Linux/musl in docker):** `bash tools/mesa-a9/run-tests.sh --linux`, exit 0:

| suite | result |
|---|---|
| contracts (round16 fixture bytes) | 217 checks, 0 failures |
| a9scene + freelist vs the serial-worker fake | 1522 checks, 0 failures |
| **a9fp device flow (TYPED_V3)**: success, wait floor/cap, timeout + quiet, MMU fault, capability mismatch, fence ordering, fallbacks, TPC, lints, pixel classes, the fake's V3 validator by raw ioctls | **397 checks, 0 failures** |
| a9ws vs the fake (also against the V3 header) | 1027 checks, 0 failures |
| W+0x88 program reference / V3 fields | 35 / 37 checks, 0 failures |
| `abi-v3.c` (sizes, offsets, cap bit 26, profile 4, ioctl encoding, lane constants == header) | compile pin passes |
| `a9-first-pixels --fake` exit-code arms | 39 arms, all as expected |
| **smoke script vs a stub ssh** (`tools/mesa-a9/test-smoke.sh`) | **113 checks, 0 failures** |
| shellcheck (smoke script, run-tests.sh, gen-uapi-v3.sh, test-smoke.sh) | clean, 0 findings |
| `scripts/gpu/mesa-a9-check.sh` (unchanged, a9ws against the docs header without V3) | passes |
| aarch64 Linux/musl: contracts, scene, a9fp, a9ws suites + `-static` binary + 8 exit arms run **from the static binary** | all pass (`RESULT MATCH` twice) |

Mutation checks on the new wait/quiet tests (a copy of the tree with one change each): hard cap 120000 -> 7 failures; one extra ioctl after the client timeout -> 1 failure; kernel-bound margin 0 -> 4 failures. All killed.

**Wait budget, aligned with the proven r97/prod98 kernel budget** (`render_wait_ms = 20000`, hard cap 30000 = the top of the kernel's 3000..30000 range; healthy TAs took 11.02 s (r95b) and 12.006 s (r96)): the normal request is **20 s**; `effective = min(30 s, max(request, 15 s floor, kernel job_timeout_ms + 3 s))`, so a 20 s kernel bound gives a 23 s wait and a 30 s bound is capped at 30 s. The command line refuses `--timeout-ms` above 30000 or below 15000 (unless `--allow-short-wait`); the library caps/raises the same way; the smoke script refuses > 30000 and kills a hung process after 75 s. A 31 s TA outlasts the cap (exit 3) in the mock.

**Quiet after a timeout (r97 semantics), mechanically asserted:** after the client's wait times out, **zero ioctls** follow it (the fake counts them): no job-status read, no fault-info read, no BO_SYNC, no readback, no unbind/destroy/GEM_CLOSE, no resubmit; only fd closes and the report file. After a *kernel-reported* job error the tool makes exactly one GET_FAULT_INFO and one GET_CONTEXT_STATUS (RAM-state reads) and nothing else. The smoke script's post-run steps are file reads over ssh and `dmesg` (kernel log reads); none touch the GPU.

## 1. THE ARTIFACT (exact)

| item | value |
|---|---|
| static device binary | `build/third_party/mesa-a9/bin/a9-first-pixels.aarch64`, 198296 bytes, ELF aarch64, statically linked, stripped, BuildID `25c6a2a9d162188b0ee19888ed7abcbbb98914a1` |
| **sha256 pin** | **`c808f897ad8c…`** in `a9-first-pixels.aarch64.sha256` (`shasum -a 256 -c` OK) and `.manifest` |
| manifest | `uapi_header_blob=ddfee6fe6f7ea2a313453583fc36084f68d6aad7`, `fixture_bounded_render_sha256=d1774e5c977a…`, `abi=TYPED_V3 (patches/gpu-render-v3 0001..0003)` |
| smoke script | `scripts/gpu/mesa-a9-device-smoke.sh` (dry run by default; `--run` = one flight); verifies the pin locally and again on the device |
| offline analyzer | `python3 -I tools/mesa-a9/analyze-smoke-raw.py <sealed raw dir>`; repeatable, never touches the device |
| regenerate | `bash tools/mesa-a9/run-tests.sh --linux` (docker `alpine:3.22`, needs network for `apk`). The prod98 lane's copy `build/gpu/prod98/mesa-a9/bin/a9-first-pixels.aarch64` (sha256 `6b3cf09e6554…`) was built from an earlier tree (120 s cap, no quiet assertion): rebuild or use this one |

The UAPI header is **not typed in the lane**: `tools/mesa-a9/gen-uapi-v3.sh` derives it from `docs/gpu/apple_g5p_drm.h` plus `patches/gpu-render-v3/workspace/0001-*.patch` into `build/third_party/mesa-a9/uapi-v3` and refuses unless the result is git blob `ddfee6fe…`. **That blob is exactly the header in prod98's kernel tree (`build/gpu/prod98/src-head/include/uapi/drm/apple_g5p_drm.h`)**, so userspace and that kernel agree on bit 26. `docs/gpu/apple_g5p_drm.h` itself is still blob `d1617fca…` (no V3) until the orchestrator applies the workspace patch; `a9ws.c` builds with or without V3 (`A9WS_HAVE_V3`).

### 1.1 Contract for the kernel lane (what the tool requires and does)

* `GET_INFO`: `version == DRM_G5P_UAPI_VERSION`, 104 B, `gpu_page_shift 14`, BVNC **9.15.6.2**, `va_start >= 0x10000`, `va_end <= 2^40`, caps `RENDER | BOUNDED_RENDER | TYPED_RENDER | SYNCOBJ | JOB_STATUS | VM_LIVE | CONTEXT_LIVE | CODE_BASE_VERIFIED | CONTEXT_STATUS` **and `DRM_G5P_CAP_TYPED_RENDER_V3 = 1<<26`** (24 is COMPUTE_BLIT_V1 and 25 FIXED_DATA_B1 on `a9/release`). `PRIME` (bit 6) is optional.
* `GET_RENDER_INFO` (120 B, input zero): `profiles` bits **2 and 4** (profile 4 = `DRM_G5P_RENDER_PROFILE_TYPED_V3`); cap bit 26 and profile bit 4 must agree or the tool exits 8; `flags` bit 0 `VARIANT_ACTIVE` must be 0 (else exit 8 before any context exists; `--allow-variant` waives); `hw_va_limit` (union at offset 104) is 0 (no statement) or 16 KiB-aligned and in `(pds_base, 2^38]` (else exit 8); `pds_base == usc_base`, `code_window >= 0x34000`, `usc_base + code_window <= 2^38`, private window page-aligned, `max_vdm_bytes >= 0x4000`; `job_timeout_ms` is read and sets the wait (§0).
* Module state for a flight: `a9_gpu_drm.render_user_experiment=1 render_user_dialect3=1`, **`render_user_wait_ms >= 15000` (the r97 value is 20000)**, no latched variant knob, `prime_experiment=1` if a dma-buf is wanted, `CAP_SYS_RAWIO`.
* The V3 submit (`SUBMIT_RENDER_TYPED`, `0xc0506454`, 80 B, unchanged): `profile 4`, `pass_size == base.size == 536`, `base.vdm_control == 0`, `ta_program_va == 0x3_0000_0100` (code BO + `A9C_W88_APPLE_B`), `ta_program_size == 0x40`, `vdm_end == vdm_size == 0x288`, `ext` all zero with `pool7/pool8` set (the V1 dialect), `reserved[4]` zero, 12 resources at the fixture VAs (highest end `0x3_0003_4000`), exactly one SIGNAL syncobj. The target BO is listed `WRITE|IMPLICIT|CACHE` when it was exported as a dma-buf before the submit, plain `WRITE` otherwise. All GPU-visible user objects end below 2^38.
* `CREATE_RENDER_TARGET` (64x64): must return `main_va/main_bytes` and `secondary_va/secondary_bytes` (the **TPC**) nonzero, 16 KiB-aligned, inside the private window and below 2^38, with `secondary_bytes == 0x4000` (else the tool refuses: exit 1 unmapped, exit 6 wrong size unless `--lax`).
* Completion contract the tool enforces: **status before fence** (`GET_JOB_STATUS = COMPLETE` must be visible once the syncobj signals, else `FENCE_ORDER`, exit 4, pixels not read); an error fence is not a completion (job `error != 0` -> exit 4 with fault info); exported sync_file and dma-buf fds must agree with the syncobj.
* Slots are not a UAPI field: the tool prints what `--dmesg` shows and the smoke analyzer checks `RENDER publish engine=0 slot=8` / `engine=1 slot=7` (the 3D line format is inferred from the TA's; absent = unproven, not failed).
* One render attachment per boot; the process never destroys the context or unbinds (kernel owns quarantine); the smoke script refuses a second `--run` on the same boot_id.

### 1.2 Contract for the Mesa lane

Use `a9ws`/`a9scene` as the winsys seam (`tools/mesa-a9/a9ws.[ch]`, `a9scene.[ch]`): V3 is `a9ws_submit.v3 / ta_program_size / vdm_end` and `a9scene_desc.v3 / ta_program_size (A9SCENE_V3_PROGRAM_BYTES 0x40) / vdm_end`, with `pass.vdm_control == 0` and the program given as `{code BO, offset}`; capability reads are `a9ws_caps.typed_v3 / v3_why / hw_va_limit / variant_active / job_timeout_ms`; render-target mappings via `a9ws_rt_create_ex`; fence fds via `a9ws_sync_export_fd`, `a9ws_bo_export`, `a9ws_fence_fd_wait` (poll, never "signalled" on its own). No private copy of any V3 definition: include the derived header. The recorder obligations are the `a9scene` lints (early block, full context record, PPP terminate, 2^38, V3 field check). The stream in V3 must be in a native (not PRIME-imported) BO.

### 1.3 Contract for the Hyprland/compositor lane

* Output of the flight: a **64x64 XR24 tile** (BGRA bytes, little-endian `0xAARRGGBB`, pitch 256, 16384 bytes) at `--out`; `--report` gives `verdict`, pixel counts and `out_sha256`. Hardware precedent (r96): `CLEAR_ONLY` (all `0xff0000ff`), exit 7; the triangle oracle is 1152 red / 2944 blue.
* Sharing: the target dma-buf is exported **before** the submit, so the job lists it `IMPLICIT|CACHE` and its fence lands in the BO's `dma_resv`; a KMS/compositor consumer that waits on implicit fences (simpledrm `prepare_fb`, or `poll(POLLIN)` on the dma-buf) is ordered after the render. An explicit **sync_file** is exported **after** the submit (`SYNCOBJ_HANDLE_TO_FD`, `EXPORT_SYNC_FILE`). A dma-buf exported after the submit carries no fence (proven in the mock) and must not be used for scanout.
* Fallbacks (never a faked completion): no PRIME -> native BO, explicit `BO_SYNC TO_CPU` after the completed job, raw readback; no sync_file -> the in-process syncobj wait stays authoritative and no fence fd is handed out.
* Constraints for an in-process compositor: render context is exclusive per device and per boot; **VM edits and render-target creation are refused (`EBUSY`) while any job is queued**, so allocators must pre-bind; every ioctl needs `CAP_SYS_RAWIO`; a job error loses the context until reboot. Presenting the tile on screen is not done here: r96's path (`a9present`, `chvt 6`, SETCRTC, frame export to the 1536x2048 canvas) remains the way, since Hyprland holds DRM master.

### 1.4 Exit codes

`a9-first-pixels`: 0 triangle MATCH; 1 setup failed (incl. TPC unmapped, scene does not fit under `hw_va_limit`); 2 usage; 3 wait timed out (do not resubmit this boot); 4 job failed / MMU fault / fence disagreement / fence before COMPLETE; 5 completed, pixels differ; 6 lint refused; 7 CLEAR_ONLY; 8 capability mismatch (no V3, half-advertised V3, unusable `hw_va_limit`, latched variant), refused before the context; 77 no render capabilities. Smoke script adds 9 (this boot already flew), 10 (no G5P render node), 11 (binary/pin, also on the device after upload), 12 (ssh/preflight failed, nothing ran), 13 (tool exit not captured: the flight may have happened).

### 1.5 Smoke capture (raw, once)

`build/gpu/mesa-a9-smoke/<UTC>/`: `preflight.txt` (kernel, boot_id, render node by driver name, module parameters), `binary.sha256.remote`, `dmesg-before/after/delta.txt`, `FLIGHT` (written **before** the run call, so a lost call still counts the boot as flown), `stdout.txt`, `stderr.txt`, `rc.txt`, `report.txt`, `out.bgra`, `pulls.txt`, `receipt.json` (facts only: ids, sha256s, ssh rc per step, `tool_runs: 1`, `tool_exit`), `SHA256SUMS`, `CLOSED`; files 0444, directory 0555. Exactly 11 ssh calls on a normal flight (preflight, upload, dmesg, run, 5 pulls, dmesg, cleanup), each once, no retry, no sleep, no analyzer. Analysis writes `<dir>.analysis.json` beside the capture (raw-file integrity, pixel class against the round16 oracle, tool-vs-analyzer cross-check, slot receipts).

## 2. The orchestrator's flight (nothing here was run on the device)

*(Device/host command block omitted; it targets the private workspace.)*
Expect exit 7 (`CLEAR_ONLY`, as r96) or 0 (triangle) on success; 8 if the kernel has no V3 (not a failure of the tool).

## 3. Remaining blockers (not userspace)

1. `docs/gpu/apple_g5p_drm.h` needs `patches/gpu-render-v3/workspace/0001-*.patch` applied (orchestrator); until then the lane derives the header.
2. A kernel with the V3 series **compiled and the typed path completing a TA**. The V3 series was never compiled or flown (its README); prod98's tree carries the V3 header but this lane did not verify that `render_user_dialect3` is wired in its `drm-render.inc`, and the proven r96 kernel is the fixed path (`render_fixed_experiment=Y`), where no typed submit has completed. The r94-r96 attach/PM recipe must exist in the typed path.
3. `render_user_wait_ms` must be set (default 12000 leaves 0.98 s over an 11.02 s TA; r96's 12.006 s completion exceeds it).
4. PM free-stack base `0xE1_C026_4000` is above 2^38 and kernel-private; `hw_va_limit` describes user ranges only.
5. `ACCESS_CACHE` on a native exported BO only maintains caches if the shmem `sgt` exists (`g5p_render_cache` skips when NULL); read from `patches/gpu-render/0002`, unverified on hardware.
6. The `--run` path is verified only against the stub ssh. Real `sudo -n`, `timeout`, `dmesg` and driver naming (`apple-g5p-drm`, module `a9_gpu_drm`) are assumptions from the docs and kernel logs.

## 4. Files (all under `tools/mesa-a9/` unless noted)

`gen-uapi-v3.sh`, `abi-v3.c`, `abi-proposal-v3.c` (bit 26), `a9ws.[ch]`, `a9scene.[ch]`, `a9fix.h` (CLEAR_ONLY), `a9fake.h`, `a9fp.h` (new, the flow as a library), `a9-first-pixels.c` (its CLI), `test-a9fp.c`, `test-a9ws.c` (one initializer), `test-smoke.sh`, `analyze-smoke-raw.py`, `run-tests.sh`; `scripts/gpu/mesa-a9-device-smoke.sh`; this file. The scene is the round16 fixture; the mock proves marshalling, refusal and ordering only.
