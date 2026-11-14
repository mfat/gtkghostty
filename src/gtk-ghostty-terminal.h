/* GtkGhosttyTerminal: a GTK4 terminal view over libghostty-vt.
 *
 * The widget renders a terminal byte stream the caller feeds it and reports
 * what should go back to the program. It never starts a process or opens a
 * PTY: connect GtkGhosttyTerminal::input and ::reply to your transport.
 */
#pragma once

#include <gtk/gtk.h>

G_BEGIN_DECLS

#define GTK_GHOSTTY_TYPE_TERMINAL (gtk_ghostty_terminal_get_type ())
G_DECLARE_FINAL_TYPE (GtkGhosttyTerminal, gtk_ghostty_terminal, GTK_GHOSTTY, TERMINAL, GtkWidget)

GtkWidget  *gtk_ghostty_terminal_new                (void);

void        gtk_ghostty_terminal_feed               (GtkGhosttyTerminal         *self,
                                                     GBytes                     *data);
void        gtk_ghostty_terminal_feed_data          (GtkGhosttyTerminal         *self,
                                                     const guint8               *data,
                                                     gsize                       length);

void        gtk_ghostty_terminal_paste_text         (GtkGhosttyTerminal         *self,
                                                     const char                 *text);
gboolean    gtk_ghostty_terminal_paste_is_safe      (const char                 *text);

char       *gtk_ghostty_terminal_get_text           (GtkGhosttyTerminal         *self);

guint       gtk_ghostty_terminal_get_columns        (GtkGhosttyTerminal         *self);
guint       gtk_ghostty_terminal_get_rows           (GtkGhosttyTerminal         *self);
void        gtk_ghostty_terminal_set_grid_size      (GtkGhosttyTerminal         *self,
                                                     guint                       columns,
                                                     guint                       rows);

const char *gtk_ghostty_terminal_get_title          (GtkGhosttyTerminal         *self);

void        gtk_ghostty_terminal_set_font_desc      (GtkGhosttyTerminal         *self,
                                                     const PangoFontDescription *font_desc);
PangoFontDescription *
            gtk_ghostty_terminal_get_font_desc      (GtkGhosttyTerminal         *self);

gboolean    gtk_ghostty_terminal_get_legacy_keyboard (GtkGhosttyTerminal        *self);
void        gtk_ghostty_terminal_set_legacy_keyboard (GtkGhosttyTerminal        *self,
                                                      gboolean                   legacy);

gboolean    gtk_ghostty_terminal_get_pull_history_on_grow (GtkGhosttyTerminal   *self);
void        gtk_ghostty_terminal_set_pull_history_on_grow (GtkGhosttyTerminal   *self,
                                                           gboolean              pull);

G_END_DECLS
