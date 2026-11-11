#!/usr/bin/env bash
# Compile Metal source with Apple's own GPU backend, offline on a Mac (no device), and split the
# result into one machine-code blob per shader. This is how we asked "what does Apple's compiler
# emit for X on this GPU?" (loop unrolling, fp16, co-issue, varyings limits, texture ops).
#
# usage: offline-compile.sh SRC.metal PIPELINES.mtlp-json OUTDIR [ARCH] [IOS_TARGET]
#   ARCH        default applegpu_g5p (A9). Others seen in the toolchain: applegpu_g9p (A10),
#               applegpu_g10p (A11). See the README for what we found about A7/A8.
#   IOS_TARGET  default 16.0. g5p needs >= 16.0 with the current toolchain (older targets
#               report "Architectures not supported for deployment target").
#   PIPELINES   names each pipeline (functions + attachment formats); see example/.
#               Its library path must be "<name>.metallib" where <name> is SRC's basename.
# Output: OUTDIR/<name>.metallib (AIR), OUTDIR/<name>_<arch>.metallib (GPU code),
#         OUTDIR/split_<arch>/NNN-stage-func.text.bin + index.tsv (macho_split.py)
# Needs Xcode with the Metal toolchain (xcrun metal, metallib, metal-tt).
# The output is Apple-compiler output: study it locally, never commit or publish it.
set -euo pipefail
SRC=$1 SCRIPT=$2 OUT=$3 ARCH=${4:-applegpu_g5p} IOS=${5:-16.0}
HERE=$(cd "$(dirname "$0")" && pwd)
NAME=$(basename "$SRC" .metal)
mkdir -p "$OUT"
[ "$SRC" -ef "$OUT/$NAME.metal" ] || cp "$SRC" "$OUT/$NAME.metal"
[ "$SCRIPT" -ef "$OUT/$NAME.mtlp-json" ] || cp "$SCRIPT" "$OUT/$NAME.mtlp-json"
cd "$OUT"
xcrun -sdk iphoneos metal -w -target "air64-apple-ios$IOS" -c "$NAME.metal" -o "$NAME.air"
xcrun -sdk iphoneos metallib "$NAME.air" -o "$NAME.metallib"
xcrun -sdk iphoneos metal-tt -arch "$ARCH" -target "air64-apple-ios$IOS" \
	"$NAME.metallib" "$NAME.mtlp-json" -o "${NAME}_${ARCH#applegpu_}.metallib"
python3 -I "$HERE/macho_split.py" "${NAME}_${ARCH#applegpu_}.metallib" "split_${ARCH#applegpu_}" | tail -1
