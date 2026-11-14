project('gtkghostty', 'c',
  version: '0.1.0',
  meson_version: '>= 1.0',
  default_options: ['c_std=c11', 'warning_level=2', 'buildtype=debugoptimized'],
)

gnome = import('gnome')

gtk = dependency('gtk4', version: '>= 4.14')
libghostty_vt = dependency('libghostty-vt', version: '>= 1.0.0')

add_project_arguments(
  '-Wno-unused-parameter',
  '-Wno-missing-field-initializers',
  language: 'c',
)

subdir('src')
