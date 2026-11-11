#!/bin/bash
# glmark2 per-scene census with GPU stats: fps, GPU busy %, GPU ms/frame, jobs/frame per scene.
#
# usage: glm-census.sh OUTDIR
#
# Measure the stack the desktop really uses. Our worst measurement mistake was running
# glmark2 with an old private Mesa stack instead of the one the compositor loaded: it
# refused scenes, lost the context and ran at half speed. So by default this copies the
# GPU-relevant environment of a running compositor process:
#   COMPOSITOR   process name to copy the environment from (default labwc; empty = none)
#   ENV_MATCH    the compositor must have this NAME=VALUE in its environment (optional),
#                e.g. ENV_MATCH=OMARCHY_G5P=1 picks our GPU session among several labwc
#   ENV_KEYS     regex of variables to copy (default: loader, Mesa, Vulkan and driver vars)
# Without a compositor environment, set the variables yourself before running.
#   STATS        debugfs stats file name (default g5p_gpu_stats; reset by writing 0)
#   SKIP         space-separated scene names to leave out
#   SCENES       override the scene list (space-separated glmark2 -b specs)
#   GLMARK2      binary (default glmark2-es2-wayland)
# Needs: passwordless sudo for debugfs and /proc/<pid>/environ, python3, gpu-stats.py next to it.
# Note: sudo strips LD_PRELOAD/LD_LIBRARY_PATH; only the debugfs reads run under sudo here.
set -u
O=${1:?usage: glm-census.sh OUTDIR}; mkdir -p "$O"
HERE=$(cd "$(dirname "$0")" && pwd)
COMPOSITOR=${COMPOSITOR-labwc}
KEYS=${ENV_KEYS:-'^(LD_LIBRARY_PATH|GBM_BACKEND|GBM_BACKENDS_PATH|LIBGL_DRIVERS_PATH|__EGL_VENDOR_LIBRARY_FILENAMES|VK_[A-Z_]+|PVR_[A-Z0-9_]+|MESA_[A-Z_]+|GALLIUM_[A-Z_]+|DRIRC_CONFIGDIR|ZINK_[A-Z_]+|XDG_RUNTIME_DIR|WAYLAND_DISPLAY)='}
if [ -n "$COMPOSITOR" ]; then
  P=
  for p in $(pgrep -x "$COMPOSITOR"); do
    if [ -z "${ENV_MATCH:-}" ] || sudo -n sh -c "tr '\0' '\n' < /proc/$p/environ" | grep -qx "$ENV_MATCH"; then P=$p; fi
  done
  [ -n "$P" ] || { echo "no $COMPOSITOR process${ENV_MATCH:+ with $ENV_MATCH}"; exit 1; }
  sudo -n sh -c "tr '\0' '\n' < /proc/$P/environ" | grep -E "$KEYS" > "$O/env.txt"
  while IFS= read -r l; do export "$l"; done < "$O/env.txt"
fi
: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}" "${WAYLAND_DISPLAY:=wayland-0}"
export XDG_RUNTIME_DIR WAYLAND_DISPLAY
S=$(sudo -n find /sys/kernel/debug/dri -name "${STATS:-g5p_gpu_stats}" -print -quit)
[ -n "$S" ] || echo "warning: no ${STATS:-g5p_gpu_stats} in debugfs; fps only"
G=${GLMARK2:-glmark2-es2-wayland}
SC=${SCENES:-'build:use-vbo=true texture:texture-filter=linear shading:shading=phong bump:bump-render=normals
 effect2d:kernel=0,1,0;1,-4,1;0,1,0; pulsar:quads=5 desktop:effect=blur:blur-radius=5:passes=1:separable=true:windows=4
 buffer:update-method=map ideas:speed=duration jellyfish terrain shadow refract conditionals:fragment-steps=5
 function:fragment-steps=5 loop:fragment-steps=5'}
for b in $SC; do
  n=${b%%:*}
  case " ${SKIP:-} " in *" $n "*) echo "$n skipped"; continue ;; esac
  [ -n "$S" ] && sudo -n sh -c "echo 0 > $S"
  u0=$(cut -d' ' -f1 /proc/uptime); t0=$(date +%s%N)
  timeout -s KILL 60 "$G" --fullscreen -b "$b" > "$O/$n.log" 2>&1; rc=$?   # KILL: a hung client ignores TERM
  t1=$(date +%s%N); u1=$(cut -d' ' -f1 /proc/uptime)
  [ -n "$S" ] && sudo -n cat "$S" > "$O/$n.stats"
  fps=$(grep -oE "FPS: [0-9]+" "$O/$n.log" | head -1 | cut -d" " -f2); fps=${fps:-0}
  # glmark2 runs each scene for 10 s by default, so frames = fps * 10.
  line="$n rc=$rc fps=$fps up=$u0-$u1"
  if [ -n "$S" ] && [ "$fps" != 0 ]; then
    line="$line $(python3 "$HERE/gpu-stats.py" "$O/$n.stats" --frames $((fps * 10)) --window-ms $(( (t1 - t0) / 1000000 )))"
  fi
  echo "$line" | tee -a "$O/census.txt"
  sleep 3
done
