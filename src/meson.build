# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
api_version = '1'

public_headers = files('gtkghostty.h', 'gtk-ghostty-terminal.h', 'gtk-ghostty-pty.h', 'gtk-ghostty-visibility.h')

sources = files(
  'gtk-ghostty-terminal.c',
  'gtk-ghostty-pty.c',
  'gtk-ghostty-tables.c',
)

libgtkghostty = shared_library('gtkghostty-' + api_version,
  sources,
  dependencies: [gtk, libghostty_vt],
  c_args: ['-DG_LOG_DOMAIN="GtkGhostty"', '-DGTK_GHOSTTY_COMPILATION'],
  gnu_symbol_visibility: 'hidden',
  install: true,
)

install_headers(public_headers, subdir: 'gtkghostty-' + api_version)

gtkghostty_dep = declare_dependency(
  link_with: libgtkghostty,
  include_directories: include_directories('.'),
  dependencies: [gtk],
)

if get_option('introspection')
  gnome.generate_gir(libgtkghostty,
    sources: public_headers + files('gtk-ghostty-terminal.c', 'gtk-ghostty-pty.c'),
    namespace: 'GtkGhostty',
    nsversion: api_version,
    identifier_prefix: 'GtkGhostty',
    symbol_prefix: 'gtk_ghostty',
    includes: ['Gtk-4.0'],
    header: 'gtkghostty.h',
    install: true,
  )
endif

import('pkgconfig').generate(libgtkghostty,
  name: 'gtkghostty',
  description: 'GTK4 terminal widget over libghostty-vt',
  subdirs: 'gtkghostty-' + api_version,
  requires: ['gtk4'],
  requires_private: ['libghostty-vt'],
)
