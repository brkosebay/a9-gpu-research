# r96 device result: first natural TA→3D render, shown on screen (2026-10-30)

Entry `tri96-8d67f9292d`, payload sha256 `04429ad905d0…`.
Each attempt was a fresh DFU cold boot, stage 1 (slot-7 3D published with no doorbell).

| Campaign | TA | 3D | Outcome |
|---|---|---|---|
| r95b `20261030T162028Z` | complete (stamp 1/1, PM saved) | not part of r95b | region image populated (254 nz bytes), SoC alive |
| r96 `20261030T163206Z` | consumed, **not complete** (last=-110, ~12k IRQs) | not submitted | SoC froze |
| r96 `20261030T163838Z` | submitted/consumed/complete | submitted/consumed/complete | **64×64 XR24 target fully blue: 4096/4096 pixels, 0 untouched**; capture sha matches the kernel receipt; failed=0; SoC alive |

The `render_status pixels=0` field is a legacy observer reading the wrong field.
The sealed target capture decides the result.

Natural TA completion varies across cold boots of the same payload: 2 of 3 boots
completed. The r95b/r96 timing analysis of the stalled boot is open.

## On-screen presentation

Done on the live r96 epoch, with no further GPU command. `a9present`
(build/gpu-present-a9/aarch64) shows the exported 1536×2048 XR24 canvas
(build/gpu/round96/frame-20261030T163838Z/) via SETCRTC on simpledrm. Hyprland
holds DRM master, so the first attempt failed with EACCES. The working sequence:

*(Device/host command block omitted; it targets the private workspace.)*

Result: `PASS A9P_PRESENT seq=0 mode=copy method=setcrtc present_us=11511`, then
`A9P RESTORE ... result=0`. The owner confirmed the blue frame on the iPad.

Next: r97, a non-clear triangle scene whose output depends on geometry, on the
same r96 path.
