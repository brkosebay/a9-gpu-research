# Tools

Small, self-contained scripts from our A9 (G5P) work that are useful to anyone bringing up Linux on an older
Apple PowerVR GPU. They are cleaned-up copies of what we actually ran, with paths and chip names turned
into arguments. Licence: **MIT** ([LICENSE.md](LICENSE.md)).

**None of these tools' outputs are in this repository, and yours should not be in any public repository
either.** The firmware extractor and the Metal compiler probe produce Apple code and Apple-compiler output:
study them locally and write up what you learn in your own words.

| Tool | Runs on | What it is for |
|---|---|---|
| [firmware/extract-kext-firmware.py](firmware/extract-kext-firmware.py) | any host, Python 3 stdlib | Split the AGX kexts and the GPU firmware out of a prelinked kernelcache; decode the firmware's META LDR records |
| [firmware/build-metag-binutils.sh](firmware/build-metag-binutils.sh) | Linux, or Docker | Build a META-capable `objdump` (binutils 2.30, the last release with metag) |
| [firmware/disassemble-ldr.py](firmware/disassemble-ldr.py) | any host (+ objdump) | Rebuild the firmware's memory regions from the LDR records and disassemble them |
| [firmware/minim.py](firmware/minim.py) | any host (+ objdump) | Expand MINIM (META's compressed encodings) to standard META so `objdump` can read it; provisional |
| [census/glm-census.sh](census/glm-census.sh) | the Linux device | glmark2 per scene: fps, GPU busy %, GPU ms/frame, jobs/frame, in the compositor's real environment |
| [census/gpu-stats.py](census/gpu-stats.py) | anywhere | Parse our driver's `g5p_gpu_stats` debugfs snapshot into GPU ms and busy % |
| [metal/offline-compile.sh](metal/offline-compile.sh) | macOS with Xcode | Compile Metal with Apple's own GPU backend offline and split it per shader |
| [metal/macho_split.py](metal/macho_split.py) | any host | Split GPU Mach-O objects out of a compiled metallib or binary archive |
| [ram/ram-census.sh](ram/ram-census.sh) | the Linux device | Read-only RAM snapshot with GPU BO inventory, PSS per process, zram and PSI |

## Firmware: kernelcache to readable META code

Apple's GPU firmware ships inside the kernelcache, in the firmware kext's `__TEXT,__const` section, as an
Imagination META "LDR" image. The A9 firmware runs on a META core next to the GPU.

```text
extract-kext-firmware.py KERNELCACHE --list          # which AGX bundle ids exist (pick --gpu)
extract-kext-firmware.py KERNELCACHE OUT --gpu G5P   # kexts, sections, agx-g5p-c0.ldr, meta-ldr.json, strings.tsv
build-metag-binutils.sh ~/metag                      # once; DOCKER_IMAGE=<linux image> on macOS
disassemble-ldr.py OUT REGIONS --objdump ~/metag/bin/metag-linux-objdump
minim.py REGIONS --objdump ~/metag/bin/metag-linux-objdump
```

- KERNELCACHE is the decompressed arm64 Mach-O from the restore image for your device and iOS version.
  The extractor handles the old *prelinked* layout (`__PRELINK_INFO`). The A9's iOS 16.7.10 kernelcache
  uses it [V], and we expect the older A7/A8 kernelcaches to use it too [I]. It refuses the newer
  MH_FILESET layout.
- We have only run this on the A9 (iOS 16.7.10, bundle ids `com.apple.AGXG5P` and
  `com.apple.AGXFirmwareKextG5P`). On another chip, run `--list` and pass the suffix you see. Then check two
  things before you trust the output: that the firmware kext's `requestFirmwareBinary` returns the
  `__TEXT,__const` pointer and length, and that the blob starts with the META LDR device id the decoder checks.
- `strings.tsv` (the kext `__cstring` strings plus the strings inside the LDR) is a good starting index for
  Ghidra. The kext's strings name many methods, and the LDR carries a few firmware strings and labels (e.g.
  `META FW started!`).
- Most of the A9 firmware's code is MINIM, which plain `objdump` decodes as garbage. `minim.py` expands
  the general-purpose subset following the public META HTP TRM. Its decodes are provisional. The docstring
  explains the storage-order trap: a 16-bit instruction is a little-endian halfword, not the byte pair as printed.
- For the kexts, load `<kext>.macho` into Ghidra as AARCH64 at its original VAs.

## Measuring: GPU ms/frame, not just fps

`census/glm-census.sh` runs a fixed list of glmark2 scenes. For each one it records fps, GPU busy %, GPU
ms/frame and jobs/frame, and the `up=` uptime window, so you can line the scene up with kernel log
events. It copies the GPU-relevant environment from a running compositor (labwc by default;
`ENV_MATCH` picks one session). That way you measure the Mesa the desktop actually loads, not a stale
private build.
`census/gpu-stats.py` is the parser. Its docstring describes the counters, so you can add the same
counters to your own driver: per-job firmware start and end stamps per engine, in a snapshot you can reset.

## Shader questions: ask Apple's compiler

`metal/offline-compile.sh` uses the Xcode Metal toolchain's `metal-tt` with `-arch applegpu_g5p` to turn Metal
source into the exact GPU code the iOS driver would load. `macho_split.py` then splits it into one blob
per shader. `example/` has a vertex+fragment triangle and a compute kernel. We used this to answer questions
like "does Apple unroll this loop?" or "how many varyings fit?". A one-factor change in the
Metal source lets you diff the outputs.

What we found about other generations (Xcode Metal toolchain 27.1, 2026-11-11):
- A strings scan of one of the toolchain's GPU backend libraries lists the architecture names `applegpu_g4p`
  and `applegpu_g4g`. [V]
- `metal-tt -arch applegpu_g4p` (and `g4g`) reports "No available translator". [V] That these two names
  mean A8 and A8X is our guess. [I]
- `applegpu_g5p` compiles only with deployment target iOS 16.0 or later. [V]
- An A8 port therefore needs another reference compiler: an older Xcode, or the compiler in the device's
  own iOS, on a device you own. [I]

## RAM

`ram/ram-census.sh LABEL` prints a read-only snapshot to stdout: meminfo, iomem, memblock, the GPU BO
inventory from debugfs, PSS per process, zram, PSI and reclaim counters. Take one at idle and one under
load, and diff them. The rules that kept our numbers honest are printed at the end. Views overlap, so don't
sum them; BO counters are device-wide, so don't multiply them per client. The output contains your boot id and
kernel command line, so don't publish it raw.

## Before you run anything on a device

- The device-side scripts use `sudo -n` only for debugfs and `/proc/<pid>/environ`. `sudo` strips
  `LD_LIBRARY_PATH` and `LD_PRELOAD`, so a GPU client started under sudo silently loads a different Mesa.
- Copying scripts to the device can lose the executable bit. Run them as `bash script.sh`.
