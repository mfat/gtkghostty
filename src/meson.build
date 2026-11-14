api_version = '1'

public_headers = files('gtkghostty.h', 'gtk-ghostty-terminal.h')

sources = files(
  'gtk-ghostty-terminal.c',
  'gtk-ghostty-tables.c',
)

libgtkghostty = shared_library('gtkghostty-' + api_version,
  sources,
  dependencies: [gtk, libghostty_vt],
  c_args: ['-DG_LOG_DOMAIN="GtkGhostty"'],
  gnu_symbol_visibility: 'default',
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
    sources: public_headers + files('gtk-ghostty-terminal.c'),
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
