#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
#
# Build libghostty-vt for Linux and package it for applications that bundle
# it without building Zig themselves (SSH Pilot's deb, rpm and AppImage):
#
#   packaging/linux/package-libghostty-vt.sh x86_64|aarch64 OUTDIR
#
# Writes OUTDIR/libghostty-vt-<version>-linux-<arch>.tar.gz and its .sha256.
# The library targets glibc 2.31 (Ubuntu 20.04, Debian 11, RHEL 9 and newer)
# with a baseline CPU, so one archive per architecture runs on every current
# distribution. The archive is relocatable: its pkg-config file finds the
# library and headers relative to itself.
set -eu

arch=${1:?usage: $0 x86_64|aarch64 OUTDIR}
out=${2:?usage: $0 x86_64|aarch64 OUTDIR}
glibc=2.31
here=$(cd "$(dirname "$0")/../.." && pwd)
case $arch in x86_64|aarch64) ;; *) echo "unsupported arch: $arch" >&2; exit 2 ;; esac

version=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' "$here/packaging/windows/build-libghostty-vt.py")
name=libghostty-vt-$version-linux-$arch
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
prefix=$work/$name

python3 "$here/packaging/windows/build-libghostty-vt.py" \
    --target "$arch-linux-gnu.$glibc" --prefix "$prefix"

# Relocatable pkg-config files; the static archive stays out (the bundle is
# for linking the shared library), and so does CMake's absolute config.
for pc in "$prefix"/lib/pkgconfig/*.pc; do
    sed -i "s|^prefix=.*|prefix=\${pcfiledir}/../..|" "$pc"
done
rm -rf "$prefix/lib/cmake" "$prefix"/lib/*.a "$prefix/lib/pkgconfig/libghostty-vt-static.pc"
sed -i '/^Requires.private: libghostty-vt-static.pc/d' "$prefix/lib/pkgconfig/libghostty-vt.pc"

# Refuse an archive that needs a newer glibc than promised.
newest=$(objdump -T "$prefix/lib/libghostty-vt.so.$version" | grep -oE 'GLIBC_[0-9.]+' | sed 's/GLIBC_//' | sort -uV | tail -1)
if [ "$(printf '%s\n%s\n' "$newest" "$glibc" | sort -V | tail -1)" != "$glibc" ]; then
    echo "error: needs glibc $newest, more than the promised $glibc" >&2
    exit 1
fi
printf 'libghostty-vt %s for %s-linux-gnu, glibc >= %s (newest symbol GLIBC_%s)\n' \
    "$version" "$arch" "$glibc" "$newest" >> "$prefix/share/licenses/libghostty-vt/SOURCE"

mkdir -p "$out"
tar -C "$work" --owner=0 --group=0 --numeric-owner -czf "$out/$name.tar.gz" "$name"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256" && cat "$name.tar.gz.sha256")
