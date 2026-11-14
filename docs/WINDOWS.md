# Building on Windows (verified 2026-11-14)

Verified on Windows 10 22H2 (VirtualBox, no GPU) with MSVC 19.44 (VS 2022 Build Tools),
python.org Python 3.14 and the gvsbuild GTK 4.22.4 runtime that SSH Pilot uses. The library,
GIR and typelib build with no compiler warnings; `tests/test_terminal.py` passes (7/7) when
run from the interactive desktop session, and the showcase fixture renders.

## Inputs

- **GTK 4**: a gvsbuild bundle (headers, `.lib` import libraries, `lib/pkgconfig`,
  `pkg-config.exe`, `g-ir-scanner`, and the PyGObject wheels for the same Python).
- **libghostty-vt 1.0**: `ghostty-vt.dll`, `ghostty-vt.lib` and `include/`, built with Zig 0.17
  for `x86_64-windows-gnu` (cross-compiling from Linux works). The release does not ship a
  `.pc` file with a Windows prefix; write one:

  ```
  prefix=C:/path/to/ghostty-vt
  includedir=${prefix}/include
  libdir=${prefix}/lib
  Name: ghostty-vt
  Description: Ghostty VT library
  Version: 1.0.0
  Cflags: -I${includedir}
  Libs: -L${libdir} -lghostty-vt
  ```

- **Meson and Ninja** from pip, plus **setuptools**: gvsbuild's `g-ir-scanner` still imports
  `distutils`, which Python 3.12 removed; setuptools provides it.

## Two traps

1. gvsbuild's `bin\g-ir-scanner` starts with the Python path of gvsbuild's own CI machine
   (`D:\a\gvsbuild\...`). Point Meson at it through a native file:

   ```ini
   [binaries]
   g-ir-scanner = ['C:/path/to/venv/Scripts/python.exe', 'C:/path/to/gtk/bin/g-ir-scanner']
   ```

   The Python must match the scanner's `_giscanner.cp3XX` module (3.14 here).
2. MSVC only writes an import library for a DLL that exports something: every public
   symbol carries `GTK_GHOSTTY_API` (`src/gtk-ghostty-visibility.h`), or linking the
   introspection dumper fails with LNK1181 on `gtkghostty-1.lib`.

## Build

From a Developer Command Prompt (or after `vcvars64.bat`):

```bat
set "PATH=%GTK%\bin;%GHOSTTY%\bin;%VENV%\Scripts;%PATH%"
set "PKG_CONFIG_PATH=%GTK%\lib\pkgconfig;%GHOSTTY%\lib\pkgconfig"
set "LIB=%GTK%\lib;%LIB%"
set "INCLUDE=%GTK%\include;%INCLUDE%"
meson setup _build --buildtype=release --native-file native.ini
ninja -C _build
```

Run with `_build\src`, the libghostty-vt `bin` and GTK's `bin` on `PATH` and
`GI_TYPELIB_PATH=_build\src`. GUI tests must run in the logged-in desktop session; over SSH,
GTK crashes with an access violation before any test code runs.

## Open items found on Windows

- **Korean (Hangul) shows as hex boxes** with the default `Monospace` font (Courier New), although
  Malgun Gothic is installed; CJK ideographs, kana and emoji fall back correctly. Pango's Windows
  font fallback, not the widget; needs a look at the fallback chain or a better default font.
- The test VM renders with GTK's Cairo renderer (no GPU); real hardware is untested.
- No PTY demo yet: the ConPTY adapter is still to come (`examples/pty_demo.py --fixture` works).
