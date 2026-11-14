/* Symbol visibility for the gtkghostty library. */
#pragma once

#if defined(_WIN32) || defined(__CYGWIN__)
#  ifdef GTK_GHOSTTY_COMPILATION
#    define GTK_GHOSTTY_API __declspec(dllexport) extern
#  else
#    define GTK_GHOSTTY_API __declspec(dllimport) extern
#  endif
#else
#  define GTK_GHOSTTY_API __attribute__((visibility("default"))) extern
#endif
