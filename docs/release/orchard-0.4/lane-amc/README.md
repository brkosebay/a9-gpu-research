# Lane CLPC-int: AMC PMU / integration-i

Prepared 2026-11-11. No device access, no publish, no workspace commit, no
CHANGELOG edit, no m1n1 tree access. Hardware validation remains outstanding.
The owner's instruction supersedes the earlier private-DT restriction in
`docs/power/clpc-20261111.md`: ordinary MMIO addresses belong in the shared dtsi.
No ADT dump, calibration or firmware data is exported.

## Topics and exported patches

Orchard `j71t-04/amc-pmu`: **b52d4435e60a014a4504c850f575598710d05c7a**,
based on SOC **eecad635ddf08c02f154112c20e666b0732aca81**.
Worktree: `build/orchard-0.4/lane-amc/orchard`.
Current fetched `origin/main`: `f825c5782f31cc4754f7907662aa7e1099c1ed0d`.
The next free perf numbers are 0001–0002; S8000 0007 belongs to the SOC dependency,
so this topic's node is 0008. These must follow SOC when landing.

Kernel `j71t-04/amc-pmu`, Docker `linux-a9-src:/src/orchard04-lane-amc`,
based on SOC `ab2fdae02fa3319dd014461c80e65481488eddc5`:

| Kernel SHA | Change |
| --- | --- |
| `272290de263a5368cc2343ae9714c5c2b6f14936` | Binding (cherry-picked from `dab287071`) |
| `a91849a0215598e65c0dcdbe89a38b7d4bf66a88` | Driver/Kconfig/Makefile (from `ca12a2ecd`) |
| `9dfe37b4410a90d61907180149eab70c717771c6` | Shared S8000/S8003 MCC port-monitor node |

All three use the global author, upstream subjects and `Assisted-by: LLM`,
with no Signed-off-by. Exported by Orchard `tools/kernel-tree/export.py`
(`--base ab2fdae02 --topic 9dfe37b44=devices/s8000`); exporter verified the
three patches reproduce the topic tree exactly:

- `kernel/patches/devices/s8000/0008-arm64-dts-apple-s800-0-3-Add-the-memory-port-monitor.patch`
- `kernel/patches/drivers/perf/0001-dt-bindings-perf-Add-Apple-A9-port-bandwidth-monitor.patch`
- `kernel/patches/drivers/perf/0002-perf-apple-Add-A9-memory-port-byte-counters.patch`

`CONFIG_APPLE_AMC_PMU=y` in apple-16k; explicitly unset in apple-4k.
Both configs resolved with `olddefconfig`, ARCH=arm64, LLVM=-19 using Orchard's
bookworm toolchain. Only one config line changes in each. Device/chip TOML
comments mark the feature not device-proven; no support-status promotion.
`tools/catalog/generate matrix` ran and generated no matrix diff.
No machine compatibility checks or hardware module parameters added.

## Integration and build receipt

Orchard `j71t-04/amc-pmu-integration-i`:
**fac8ee2aa04bc0a4909051ebda5f04b3dbec3a26**.
Worktree `build/orchard-0.4/lane-amc/orchard-i`, a merge of h2
`49848ce` (`j71t-04/soc-perf-integration-h2`) and the AMC topic. Merge was clean.

`df -h ~`: 63 GiB before preparation; 60 GiB immediately before build, above
10 GiB. Foreground build completed **exit 0**:

*(Device/host command block omitted; it targets the private workspace.)*

Release: `7.3.0-rc1-orchard-apple-16k-topic-integration04i`.
Image.gz, modules and DTBs built; 77 modules staged. No compiler warnings;
log includes the inherited patch whitespace warning and DTC `simple_bus_reg`
warning for `/soc/bus@20c000000` (expected `20c900000`). No MCC-node warning.
Full log: `build/orchard-0.4/lane-amc/kernel-build-i.log`.
Build receipt: `build/orchard-0.4/integration-i/build-receipt.json`.
DTB SHA256: `79f791d10d4d…`.

Packager: `scripts/orchard/package-orchard04i-integration.py`, copied/adapted
from h2. Input base is
`build/orchard-0.4/integration-h2/orchard-04-integration-h2.tar.gz`.
Output bundle:
`build/orchard-0.4/integration-i/orchard-04-integration-i.tar.gz`.
SHA256: `b96b5b5ec19d…`.

Packaging passed: per-module vermagic, DT contains both SOC and MCC nodes,
Image contains PMGR and AMC driver, initrd includes this compiled DTB and the
stable USB identity. Userspace and runner match h2's hashes byte for byte.
Tools include memclk-bw, perf60-memclk.py and amc-perf-notes.txt. The inherited
flight commands are retained and renamed, with the AMC probe appended in
`build/orchard-0.4/integration-i/DEVICE-COMMANDS.txt`.

Perf availability: no `perf` or `linux-tools` package in the saved device-root
inventory `build/omarchy/reports/packages.txt` (mtime 2026-10-22). This is stale
inventory, not proof of today's NVMe contents. Live root availability remains
**unverified** under the no-device-access rule. No package added. The first
orchestrator probe checks `command -v perf` and stops if absent.

Unit command: `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 ../../orchard/.venv/bin/python -m unittest discover -s tests -v`
in the integration-i Orchard worktree. **Exit 1: Ran 773 tests in 241.973s; FAILED (failures=7, errors=1, skipped=3)**.
Failure/error names exactly match the saved SOC baseline. These are host results, not hardware validation.
The first attempt omitted PYTHONPATH and had missing-Orchard imports (688 tests,
8 failures, 33 errors, 3 skips); it is preserved as
`build/orchard-0.4/lane-amc/unit-tests-i-missing-pythonpath.log` and is not the
baseline comparison. A second run used PYTHONPATH but system Python lacked
the package metadata supplied by Orchard’s .venv; stopped that run (exit 143),
retained `unit-tests-i-system-python.log`, then reran with SOC’s exact .venv
interpreter. Corrected log: `build/orchard-0.4/lane-amc/unit-tests-i.log`.

## PR draft

**Title:** kernel: add A9 memory traffic counters to perf

**Problem:** Linux on A9 lacks the MCC port-traffic signal used by Apple's
CLPC. Without CPU/GFX byte counters, memory-pressure measurements cannot
support a future load-driven policy or attribute traffic to those ports.

**Changes:** add a standalone DT binding and the apple_amc fixed-event PMU,
then describe the MCC monitor in the shared S8000/S8003 dtsi. Expose system-wide
CPU read/write and GFX read/write byte counts; retain CPU-read's two physical
slots and decoded scaling. A 10 ms timer drains counters while events run;
CPU hotplug and suspend/resume paths preserve perf ownership and reprogramming.
Enable the driver in apple-16k. This supplies telemetry only; it changes no
frequency policy and adds no governor. Counts represent MCC-port bytes, not
necessarily DRAM-pin traffic. Read/clear loss and accuracy need hardware checks.

**Other devices affected:** every S8000/S8003 board including the common dtsi
gets the node (all iPhone/iPad boards using it, not just J71t). Every apple-16k
kernel enables the driver; only matching DTs bind it. Apple-4k leaves it off.
No working-status promotion is claimed for any board.

**Dependencies and merge order:** land `j71t-04/soc-perf` (`eecad63`, kernel
through `ab2fdae02`) first, then `j71t-04/amc-pmu` (`b52d443`, kernel through
`9dfe37b44`). The DT patch follows SOC's devices/s8000 0007. Integration-i
is a local validation merge on integration-h2, not a PR topic to land wholesale.
Prepare only; publish nothing until the orchestrator/owner approves.

**Validation:** integration-i builds Image.gz/modules/DTBs and packages
successfully; unit result below. Device probe, simultaneous four-event counting,
CPU/GFX attribution, states 12/13/12, suspend/resume and CPU hotplug still required.
Few-percent byte calibration remains unimplemented/unflown (CLPC §4.3); smoke
numbers cannot justify a governor. No hardware result is claimed.

**Proposed CHANGELOG line:** Add A9 CPU and graphics memory-port byte counters
through perf's apple_amc PMU (S8000/S8003; hardware validation pending).
