# Building

gtkghostty needs GTK ≥ 4.14, GObject Introspection, Meson, a C compiler and libghostty-vt 1.0.
Every recipe below is run by CI or was checked in a clean container.

## 1. libghostty-vt

`packaging/windows/build-libghostty-vt.py` builds libghostty-vt 1.0.0 from the official release
on Linux, macOS and Windows. It downloads the Zig version the release needs, checks every
download's SHA-256, and installs the library, headers and pkg-config file into a prefix:

```sh
python3 packaging/windows/build-libghostty-vt.py --target native --prefix ~/.local/opt/ghostty-vt
```

It takes about 6 minutes. No Zig or other tools need to be installed first.

## 2. Linux

Install the build tools and GTK development files. For the tests you also need Xvfb, xdotool and
pytest.

| Distribution | Packages |
|---|---|
| Debian 13, Ubuntu 24.04 | `meson ninja-build gcc pkgconf libgtk-4-dev gobject-introspection libgirepository1.0-dev python3-gi gir1.2-gtk-4.0` · tests: `python3-pytest xvfb xauth xdotool x11-xserver-utils` |
| Fedora 44 | `meson ninja-build gcc pkgconf-pkg-config gtk4-devel gobject-introspection-devel python3-gobject` · tests: `python3-pytest xorg-x11-server-Xvfb xauth xdotool xmodmap` |
| Arch | `meson ninja gcc pkgconf gtk4 gobject-introspection python-gobject` · tests: `python-pytest xorg-server-xvfb xorg-xauth xdotool xorg-xmodmap` |

Then:

```sh
PKG_CONFIG_PATH=~/.local/opt/ghostty-vt/lib/pkgconfig meson setup _build
ninja -C _build
```

Install it with `meson setup _build --prefix=/usr/local` and `meson install -C _build`. An
application that ships its own copy adds `-Dprivate_libdir=myapp`: only the library and typelib
are installed, into `<libdir>/myapp`. Or run it from the build tree:

```sh
export GI_TYPELIB_PATH=$PWD/_build/src
export LD_LIBRARY_PATH=$PWD/_build/src:$HOME/.local/opt/ghostty-vt/lib
python3 examples/pty_demo.py
```

## 3. macOS

With [Homebrew](https://brew.sh):

```sh
brew install meson ninja pkgconf gtk4 gobject-introspection pygobject3
python3 packaging/windows/build-libghostty-vt.py --target native --prefix ~/.local/opt/ghostty-vt
PKG_CONFIG_PATH=~/.local/opt/ghostty-vt/lib/pkgconfig meson setup _build
ninja -C _build
```

To run from the build tree, set `GI_TYPELIB_PATH` as on Linux and `DYLD_LIBRARY_PATH` instead of
`LD_LIBRARY_PATH`.

## 4. Windows

Windows builds use Visual Studio and a [gvsbuild](https://github.com/wingtk/gvsbuild) GTK
release, for applications that ship gvsbuild's GTK with python.org Python. From a Visual Studio
x64 developer prompt with Python 3.14 and `pip install meson ninja setuptools`:

```powershell
packaging\windows\build-gvsbuild.ps1
```

The script fetches the pinned gvsbuild GTK, builds libghostty-vt and the widget, checks that the
widget loads in gvsbuild's PyGObject, and writes
`gtkghostty-<version>-gvsbuild-<gvsbuild version>-x64.zip` (the zip each release carries).

Two things the script handles, in case you build by hand:

- gvsbuild's `bin\g-ir-scanner` names the Python of gvsbuild's own CI machine. Run it with yours
  through a Meson native file
  (`g-ir-scanner = ['C:/path/to/python.exe', 'C:/path/to/gtk/bin/g-ir-scanner']`), and install
  `setuptools`: the scanner still imports `distutils`.
- Every public symbol carries `GTK_GHOSTTY_API`; without it MSVC writes no import library and
  linking fails with LNK1181.

GTK programs must run in the logged-in desktop session; over SSH they fail before any code runs.

## Tests

```sh
LIBGHOSTTY_VT_LIBDIR=~/.local/opt/ghostty-vt/lib xvfb-run -a tests/run.sh _build
```

On macOS and Windows, run `tests/run.sh _build` (or `python -m pytest tests` with the paths set)
without `xvfb-run`; the keyboard tests need X11 and skip there.

After changing the public API, regenerate the Python stubs (a test fails until you do):

```sh
python3 tools/gen_stubs.py _build/src/GtkGhostty-1.gir
```
