# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
#
# Build gtkghostty with Visual Studio against a gvsbuild GTK 4 release, for
# applications that ship gvsbuild's GTK with python.org Python (MSYS2 builds
# cannot be mixed with it). Produces
# gtkghostty-<version>-gvsbuild-<gvsbuild version>-x64.zip with:
#   bin\                          gtkghostty-1.dll, ghostty-vt.dll
#   lib\girepository-1.0\         GtkGhostty-1.typelib
#   share\licenses\libghostty-vt\ LICENSE, third-party.json, SOURCE
#   COPYING, NOTICE
# Unzip it over the GTK prefix (or put bin on PATH and the typelib directory
# on GI_TYPELIB_PATH).
#
# Run from a Visual Studio x64 developer shell with Python 3.14 that has
# meson, ninja and setuptools (gvsbuild's g-ir-scanner is built for 3.14 and
# imports distutils, which setuptools provides).
param(
    [string]$GvsbuildVersion = "2026.8.0",
    [string]$GvsbuildSha256 = "1f95a92d037f5292da05e6ab1037032ff21ddb7b20d4ac8e83e3674c864c07b0",
    [string]$Work = "$PWD\_win"
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
# Windows PowerShell's download progress bar makes Invoke-WebRequest crawl.
$ProgressPreference = "SilentlyContinue"
$Source = (Resolve-Path "$PSScriptRoot\..\..").Path

function Get-Checked($Url, $Path, $Sha256) {
    if (-not (Test-Path $Path)) { Invoke-WebRequest -Uri $Url -OutFile $Path }
    $actual = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLower()
    if ($actual -ne $Sha256) { throw "${Path}: SHA-256 $actual, expected $Sha256" }
}

New-Item -ItemType Directory -Force $Work | Out-Null

# 1. gvsbuild GTK, extracted where its pkg-config files say it lives.
$Gtk = "C:\gtk-build\gtk\x64\release"
$zip = "$Work\GTK4_Gvsbuild_${GvsbuildVersion}_x64.zip"
Get-Checked "https://github.com/wingtk/gvsbuild/releases/download/$GvsbuildVersion/GTK4_Gvsbuild_${GvsbuildVersion}_x64.zip" $zip $GvsbuildSha256
if (-not (Test-Path "$Gtk\bin\gtk-4-1.dll")) { Expand-Archive -Force $zip $Gtk }

# 2. libghostty-vt (Zig, pinned downloads), with headers and import library.
$Vt = "$Work\ghostty-vt"
if (-not (Test-Path "$Vt\bin\ghostty-vt.dll")) {
    python "$PSScriptRoot\build-libghostty-vt.py" --prefix $Vt --cache "$Work\cache"
}

# 3. gtkghostty. gvsbuild's g-ir-scanner script names the gvsbuild CI
#    machine's Python; run it with this one instead.
$py = (Get-Command python).Source.Replace('\', '/')
$gtkFwd = $Gtk.Replace('\', '/')
@"
[binaries]
g-ir-scanner = ['$py', '$gtkFwd/bin/g-ir-scanner']
g-ir-compiler = '$gtkFwd/bin/g-ir-compiler.exe'
pkg-config = '$gtkFwd/bin/pkgconf.exe'
"@ | Set-Content -Encoding ascii "$Work\native.ini"
$env:PKG_CONFIG_PATH = "$Gtk\lib\pkgconfig;$Vt\lib\pkgconfig"
$env:PATH = "$Gtk\bin;$Vt\bin;$env:PATH"
$env:LIB = "$Gtk\lib;$Vt\lib;$env:LIB"
$env:INCLUDE = "$Gtk\include;$env:INCLUDE"
$Prefix = "$Work\prefix"
if (Test-Path "$Work\build") { Remove-Item -Recurse -Force "$Work\build" }
meson setup "$Work\build" $Source --native-file "$Work\native.ini" --buildtype=release --prefix="$Prefix"
meson compile -C "$Work\build"
meson install -C "$Work\build"

# 4. Smoke test: the widget loads and runs in gvsbuild's PyGObject.
$wheels = Get-ChildItem "$Gtk\wheels" -Filter *.whl | Where-Object { $_.Name -match "^(pygobject|pycairo)-.*-cp314-" }
python -m pip install --quiet $wheels.FullName
$env:PATH = "$Prefix\bin;$env:PATH"
$env:GI_TYPELIB_PATH = "$Prefix\lib\girepository-1.0;$Gtk\lib\girepository-1.0"
python -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('GtkGhostty', '1'); from gi.repository import GtkGhostty; t = GtkGhostty.Terminal(); t.feed_data(b'smoke'); assert t.get_text() == 'smoke'; print('GtkGhostty loads:', type(t).__name__)"

# 5. Package.
$version = (Select-String -Path "$Source\meson.build" -Pattern "version\s*:\s*'([^']+)'").Matches[0].Groups[1].Value
$stage = "$Work\stage"
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$stage\bin", "$stage\lib\girepository-1.0", "$stage\share\licenses" | Out-Null
Copy-Item "$Prefix\bin\gtkghostty-1.dll" "$stage\bin"
Copy-Item "$Vt\bin\ghostty-vt.dll" "$stage\bin"
Copy-Item "$Prefix\lib\girepository-1.0\GtkGhostty-1.typelib" "$stage\lib\girepository-1.0"
Copy-Item -Recurse "$Vt\share\licenses\libghostty-vt" "$stage\share\licenses"
Copy-Item "$Source\COPYING", "$Source\NOTICE" $stage
$out = "$PWD\gtkghostty-$version-gvsbuild-$GvsbuildVersion-x64.zip"
Compress-Archive -Force "$stage\*" $out
Get-FileHash -Algorithm SHA256 $out | ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path -Leaf $out)" } | Tee-Object "$out.sha256"
