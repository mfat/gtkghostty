#!/bin/sh
# Run the Python/GI tests against the in-tree build.
#   tests/run.sh [build dir] [pytest args...]
# LIBGHOSTTY_VT_LIBDIR: where libghostty-vt.so is, if not on the loader path.
# Headless: wrap in xvfb-run -a (and unset WAYLAND_DISPLAY, GDK_BACKEND=x11).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
build=${1:-$here/_build}
[ $# -gt 0 ] && shift
export GI_TYPELIB_PATH="$build/src${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
export LD_LIBRARY_PATH="$build/src${LIBGHOSTTY_VT_LIBDIR:+:$LIBGHOSTTY_VT_LIBDIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec python3 -m pytest -q "$here/tests" "$@"
