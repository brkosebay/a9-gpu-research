#!/bin/sh
# Build a META (metag) capable objdump for disassembling Apple's PowerVR META firmware.
# Upstream binutils dropped metag after 2.31; 2.30 still has the full META 1/2
# opcode table (opcodes/metag-dis.c).
#
# usage: build-metag-binutils.sh PREFIX
#   Builds natively (needs a C compiler, make, curl or wget). Set DOCKER_IMAGE to a
#   Linux image with a toolchain to build inside it instead (e.g. on macOS); PREFIX
#   is then mounted at /out. Result: PREFIX/bin/metag-linux-objdump.
set -eu
PREFIX=${1:?usage: build-metag-binutils.sh PREFIX}
mkdir -p "$PREFIX"
PREFIX=$(cd "$PREFIX" && pwd)
build() {  # $1 = install prefix as seen by the build
  set -eu
  cd "${TMPDIR:-/tmp}"
  if [ ! -f "$1/binutils-2.30.tar.xz" ]; then
    (command -v wget >/dev/null && wget -q -O "$1/binutils-2.30.tar.xz" https://ftp.gnu.org/gnu/binutils/binutils-2.30.tar.xz) ||
    curl -sSL -o "$1/binutils-2.30.tar.xz" https://ftp.gnu.org/gnu/binutils/binutils-2.30.tar.xz
  fi
  rm -rf binutils-2.30 metag-build && tar xf "$1/binutils-2.30.tar.xz" && mkdir metag-build && cd metag-build
  ../binutils-2.30/configure --target=metag-linux --prefix="$1" --disable-nls \
     --disable-werror --disable-gdb --disable-gprof --disable-ld --disable-gas \
     CFLAGS="-O1 -g0 -fcommon -Wno-error" >cfg.log 2>&1 || { tail -30 cfg.log; exit 1; }
  make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" all-binutils >make.log 2>&1 || { tail -40 make.log; exit 1; }
  make install-binutils >inst.log 2>&1 || { tail -20 inst.log; exit 1; }
  ls "$1/bin"
}
if [ -n "${DOCKER_IMAGE:-}" ]; then
  docker run --rm -v "$PREFIX:/out" "$DOCKER_IMAGE" sh -euc "$(sed -n '/^build() {/,/^}/p' "$0")
build /out"
else
  build "$PREFIX"
fi
