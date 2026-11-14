/* GtkGhosttyTerminal: a GTK4 terminal view over libghostty-vt 1.0.
 *
 * Terminal behaviour (parsing, screens, encoders, paste, formatter, effects)
 * is libghostty-vt's; this file is GTK glue. The drawing scheme -- one Pango
 * layout per run of same-styled cells, rebuilt only for dirty rows, glyphs
 * held to the cell grid by letter spacing, wide cells scaled to two cells,
 * box drawing on the grid -- follows tilix2 (https://github.com/markuman/tilix2,
 * WTFPL v2), moved from Cairo to GtkSnapshot.
 */

#include "gtk-ghostty-terminal.h"
#include "gtk-ghostty-tables.h"

#include <ghostty/vt.h>
#include <stdint.h>
#include <string.h>

#define DEFAULT_FONT "Monospace 11"
#define DEFAULT_COLUMNS 80
#define DEFAULT_ROWS 24
#define DEFAULT_SCROLLBACK_LINES 10000

typedef struct
{
  int x, n;
  GdkRGBA color;
} Span;

typedef struct
{
  int x, n;
  GdkRGBA fg;
  PangoLayout *layout;
  float scale;            /* wide runs: horizontal scale to exactly two cells */
  guint underline : 1;
  guint strike : 1;
  guint overline : 1;
} Run;

typedef struct
{
  int x;
  gunichar c;
  GdkRGBA fg;
} BoxCell;

typedef struct
{
  GArray *bgs;            /* Span */
  GArray *runs;           /* Run */
  GArray *boxes;          /* BoxCell */
  GPtrArray *chars;       /* char * per column, for the block cursor */
} Row;

struct _GtkGhosttyTerminal
{
  GtkWidget parent_instance;

  GhosttyTerminal terminal;
  GhosttyRenderState render_state;
  GhosttyRenderStateRowIterator rows;
  GhosttyRenderStateRowCells cells;
  GhosttyKeyEncoder key_encoder;

  GtkIMContext *im;

  PangoFontDescription *font;
  PangoFontDescription *fonts[2][2];  /* [bold][italic] */
  PangoAttrList *grid_attrs;
  int cell_width, cell_height, ascent;
  gboolean metrics_valid;

  guint columns, n_rows;
  GPtrArray *row_cache;   /* Row *, per viewport row */

  GByteArray *pending_reply;
  gboolean pending_bell, pending_title;
  char *title;

  gboolean legacy_keyboard;
  gboolean pull_history_on_grow;
  gboolean focused;
};

enum
{
  PROP_0,
  PROP_COLUMNS,
  PROP_ROWS,
  PROP_TITLE,
  PROP_LEGACY_KEYBOARD,
  PROP_PULL_HISTORY_ON_GROW,
  PROP_FONT_DESC,
  N_PROPS
};

enum
{
  SIGNAL_INPUT,
  SIGNAL_REPLY,
  SIGNAL_SIZE_CHANGED,
  SIGNAL_BELL,
  N_SIGNALS
};

static GParamSpec *properties[N_PROPS];
static guint signals[N_SIGNALS];

G_DEFINE_FINAL_TYPE (GtkGhosttyTerminal, gtk_ghostty_terminal, GTK_TYPE_WIDGET)

/* ------------------------------------------------------------------ rows */

static void
row_free (gpointer data)
{
  Row *row = data;
  for (guint i = 0; i < row->runs->len; i++)
    g_clear_object (&g_array_index (row->runs, Run, i).layout);
  g_array_unref (row->bgs);
  g_array_unref (row->runs);
  g_array_unref (row->boxes);
  g_ptr_array_unref (row->chars);
  g_free (row);
}

static Row *
row_new (void)
{
  Row *row = g_new0 (Row, 1);
  row->bgs = g_array_new (FALSE, FALSE, sizeof (Span));
  row->runs = g_array_new (FALSE, FALSE, sizeof (Run));
  row->boxes = g_array_new (FALSE, FALSE, sizeof (BoxCell));
  row->chars = g_ptr_array_new_with_free_func (g_free);
  return row;
}

static GdkRGBA
rgba (GhosttyColorRgb c)
{
  return (GdkRGBA) { c.r / 255.f, c.g / 255.f, c.b / 255.f, 1.f };
}

static gboolean
rgba_equal (const GdkRGBA *a, const GdkRGBA *b)
{
  return a->red == b->red && a->green == b->green && a->blue == b->blue && a->alpha == b->alpha;
}

/* ------------------------------------------------------------- effects */

static void
on_write_pty (GhosttyTerminal terminal, void *userdata, const uint8_t *data, size_t len)
{
  GtkGhosttyTerminal *self = userdata;
  /* Never re-enter the terminal from a callback: queue, emit after the write. */
  g_byte_array_append (self->pending_reply, data, len);
}

static void
on_bell (GhosttyTerminal terminal, void *userdata)
{
  GTK_GHOSTTY_TERMINAL (userdata)->pending_bell = TRUE;
}

static void
on_title_changed (GhosttyTerminal terminal, void *userdata)
{
  GTK_GHOSTTY_TERMINAL (userdata)->pending_title = TRUE;
}

static bool
on_device_attributes (GhosttyTerminal terminal, void *userdata, GhosttyDeviceAttributes *out)
{
  return false;  /* the library's default attributes */
}

static void
flush_effects (GtkGhosttyTerminal *self)
{
  if (self->pending_reply->len > 0)
    {
      GBytes *reply = g_bytes_new (self->pending_reply->data, self->pending_reply->len);
      g_byte_array_set_size (self->pending_reply, 0);
      g_signal_emit (self, signals[SIGNAL_REPLY], 0, reply);
      g_bytes_unref (reply);
    }
  if (self->pending_title)
    {
      GhosttyString title = { 0 };
      self->pending_title = FALSE;
      g_free (self->title);
      self->title = NULL;
      if (ghostty_terminal_get (self->terminal, GHOSTTY_TERMINAL_DATA_TITLE, &title) == GHOSTTY_SUCCESS
          && title.ptr != NULL)
        self->title = g_utf8_make_valid ((const char *) title.ptr, title.len);
      g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_TITLE]);
    }
  if (self->pending_bell)
    {
      self->pending_bell = FALSE;
      g_signal_emit (self, signals[SIGNAL_BELL], 0);
    }
}

static void
emit_input (GtkGhosttyTerminal *self, const guint8 *data, gsize len)
{
  GBytes *bytes;
  if (len == 0)
    return;
  bytes = g_bytes_new (data, len);
  g_signal_emit (self, signals[SIGNAL_INPUT], 0, bytes);
  g_bytes_unref (bytes);
}

/* ------------------------------------------------------------- metrics */

static void
ensure_metrics (GtkGhosttyTerminal *self)
{
  PangoContext *context;
  PangoLayout *probe;
  PangoRectangle logical;
  int baseline;

  if (self->metrics_valid)
    return;

  for (int bold = 0; bold < 2; bold++)
    for (int italic = 0; italic < 2; italic++)
      {
        PangoFontDescription *desc = pango_font_description_copy (self->font);
        if (bold)
          pango_font_description_set_weight (desc, PANGO_WEIGHT_BOLD);
        if (italic)
          pango_font_description_set_style (desc, PANGO_STYLE_ITALIC);
        g_clear_pointer (&self->fonts[bold][italic], pango_font_description_free);
        self->fonts[bold][italic] = desc;
      }

  context = gtk_widget_get_pango_context (GTK_WIDGET (self));
  probe = pango_layout_new (context);
  pango_layout_set_font_description (probe, self->font);
  pango_layout_set_text (probe, "M", -1);
  pango_layout_get_extents (probe, NULL, &logical);
  baseline = pango_layout_get_baseline (probe);
  g_object_unref (probe);

  self->cell_width = MAX (1, PANGO_PIXELS_CEIL (logical.width));
  self->cell_height = MAX (1, PANGO_PIXELS_CEIL (logical.height));
  self->ascent = PANGO_PIXELS (baseline);

  /* Stretch every glyph's advance to the cell (tilix2): long runs then stay
   * on the grid instead of drifting by the font's sub-pixel advance. */
  g_clear_pointer (&self->grid_attrs, pango_attr_list_unref);
  self->grid_attrs = pango_attr_list_new ();
  pango_attr_list_insert (self->grid_attrs,
                          pango_attr_letter_spacing_new (self->cell_width * PANGO_SCALE - logical.width));

  g_ptr_array_set_size (self->row_cache, 0);
  self->metrics_valid = TRUE;
}

/* ------------------------------------------------------------ geometry */

static void
apply_grid_size (GtkGhosttyTerminal *self, guint columns, guint n_rows)
{
  columns = CLAMP (columns, 1, G_MAXUINT16);
  n_rows = CLAMP (n_rows, 1, G_MAXUINT16);
  if (columns == self->columns && n_rows == self->n_rows)
    return;
  self->columns = columns;
  self->n_rows = n_rows;
  ghostty_terminal_resize (self->terminal, columns, n_rows,
                           MAX (1, self->cell_width), MAX (1, self->cell_height));
  g_ptr_array_set_size (self->row_cache, 0);
  flush_effects (self);
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_COLUMNS]);
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_ROWS]);
  g_signal_emit (self, signals[SIGNAL_SIZE_CHANGED], 0,
                 columns, n_rows, (guint) self->cell_width, (guint) self->cell_height);
  gtk_widget_queue_draw (GTK_WIDGET (self));
}

static void
gtk_ghostty_terminal_measure (GtkWidget *widget, GtkOrientation orientation, int for_size,
                              int *minimum, int *natural, int *minimum_baseline, int *natural_baseline)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (widget);
  ensure_metrics (self);
  if (orientation == GTK_ORIENTATION_HORIZONTAL)
    {
      *minimum = self->cell_width;
      *natural = self->cell_width * DEFAULT_COLUMNS;
    }
  else
    {
      *minimum = self->cell_height;
      *natural = self->cell_height * DEFAULT_ROWS;
    }
}

static void
gtk_ghostty_terminal_size_allocate (GtkWidget *widget, int width, int height, int baseline)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (widget);
  ensure_metrics (self);
  apply_grid_size (self, MAX (1, width / self->cell_width), MAX (1, height / self->cell_height));
}

/* ------------------------------------------------------------- drawing */

static void
add_bg (Row *row, int x, const GdkRGBA *color)
{
  if (row->bgs->len > 0)
    {
      Span *last = &g_array_index (row->bgs, Span, row->bgs->len - 1);
      if (last->x + last->n == x && rgba_equal (&last->color, color))
        {
          last->n++;
          return;
        }
    }
  g_array_append_val (row->bgs, ((Span) { x, 1, *color }));
}

typedef struct
{
  int x, n;
  GdkRGBA fg;
  gboolean bold, italic, wide, underline, strike, overline;
  GString *text;
} PendingRun;

static void
close_run (GtkGhosttyTerminal *self, Row *row, PendingRun *run)
{
  Run out = { 0 };
  PangoLayout *layout;
  if (run->text == NULL)
    return;
  layout = pango_layout_new (gtk_widget_get_pango_context (GTK_WIDGET (self)));
  pango_layout_set_font_description (layout, self->fonts[run->bold][run->italic]);
  pango_layout_set_text (layout, run->text->str, run->text->len);
  if (!run->wide)
    pango_layout_set_attributes (layout, self->grid_attrs);
  out.x = run->x;
  out.n = run->n;
  out.fg = run->fg;
  out.layout = layout;
  out.underline = run->underline;
  out.strike = run->strike;
  out.overline = run->overline;
  if (run->wide)
    {
      int width = 0;
      pango_layout_get_pixel_size (layout, &width, NULL);
      out.scale = (float) (2 * self->cell_width) / MAX (1, width);
    }
  g_array_append_val (row->runs, out);
  g_string_free (run->text, TRUE);
  run->text = NULL;
}

/* The current iterator row -> backgrounds, text runs and grid-drawn cells. */
static Row *
build_row (GtkGhosttyTerminal *self, const GdkRGBA *fg_default, const GdkRGBA *bg_default)
{
  Row *row = row_new ();
  GhosttyRenderStateRowSelection selection = GHOSTTY_INIT_SIZED (GhosttyRenderStateRowSelection);
  int sel_start = -1, sel_end = -1;
  uint8_t text_buf[256];
  PendingRun run = { 0 };
  int x = 0;

  ghostty_render_state_row_get (self->rows, GHOSTTY_RENDER_STATE_ROW_DATA_CELLS, &self->cells);
  if (ghostty_render_state_row_get (self->rows, GHOSTTY_RENDER_STATE_ROW_DATA_SELECTION, &selection)
      == GHOSTTY_SUCCESS)
    {
      sel_start = selection.start_x;
      sel_end = selection.end_x;
    }

  while (ghostty_render_state_row_cells_next (self->cells))
    {
      GhosttyBuffer text = { text_buf, sizeof text_buf, 0 };
      GhosttyColorRgb color;
      GdkRGBA fg = *fg_default, bg;
      gboolean has_bg = FALSE, bold = FALSE, italic = FALSE;
      gboolean underline = FALSE, strike = FALSE, overline = FALSE, invisible = FALSE;
      bool styled = false;
      const char *str = "";
      gsize len = 0;
      char *owned = NULL;

      if (ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_GRAPHEMES_UTF8,
                                              &text) == GHOSTTY_SUCCESS)
        {
          str = (const char *) text_buf;
          len = text.len;
        }
      else
        {
          str = "\xEF\xBF\xBD";  /* cluster over 256 bytes: replacement character */
          len = 3;
        }

      if (ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_BG_COLOR,
                                              &color) == GHOSTTY_SUCCESS)
        {
          bg = rgba (color);
          has_bg = TRUE;
        }
      ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_HAS_STYLING, &styled);
      if (styled)
        {
          GhosttyStyle style;
          ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_STYLE, &style);
          if (ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_FG_COLOR,
                                                  &color) == GHOSTTY_SUCCESS)
            fg = rgba (color);
          bold = (style.flags & GHOSTTY_STYLE_FLAG_BOLD) != 0;
          italic = (style.flags & GHOSTTY_STYLE_FLAG_ITALIC) != 0;
          underline = GHOSTTY_STYLE_UNDERLINE (style) != GHOSTTY_SGR_UNDERLINE_NONE;
          strike = (style.flags & GHOSTTY_STYLE_FLAG_STRIKETHROUGH) != 0;
          overline = (style.flags & GHOSTTY_STYLE_FLAG_OVERLINE) != 0;
          invisible = (style.flags & GHOSTTY_STYLE_FLAG_INVISIBLE) != 0;
          if (style.flags & GHOSTTY_STYLE_FLAG_INVERSE)
            {
              GdkRGBA old_bg = has_bg ? bg : *bg_default;
              bg = fg;
              has_bg = TRUE;
              fg = old_bg;
            }
          if (style.flags & GHOSTTY_STYLE_FLAG_FAINT)
            {
              fg.red *= 0.6f;
              fg.green *= 0.6f;
              fg.blue *= 0.6f;
            }
        }
      if (x >= sel_start && x <= sel_end)
        {
          GdkRGBA old_bg = has_bg ? bg : *bg_default;
          bg = fg;
          has_bg = TRUE;
          fg = old_bg;
        }
      if (invisible)
        len = 0;
      if (has_bg && !rgba_equal (&bg, bg_default))
        add_bg (row, x, &bg);

      owned = g_strndup (str, len);
      g_ptr_array_add (row->chars, owned);

      if (len == 0)
        close_run (self, row, &run);
      else
        {
          gunichar c = g_utf8_get_char_validated (owned, len);
          if (g_utf8_strlen (owned, len) == 1 && gtk_ghostty_box_glyph (c) != NULL)
            {
              close_run (self, row, &run);
              g_array_append_val (row->boxes, ((BoxCell) { x, c, fg }));
            }
          else
            {
              GhosttyCell raw = 0;
              GhosttyCellWide wide = GHOSTTY_CELL_WIDE_NARROW;
              gboolean is_wide;
              ghostty_render_state_row_cells_get (self->cells, GHOSTTY_RENDER_STATE_ROW_CELLS_DATA_RAW, &raw);
              ghostty_cell_get (raw, GHOSTTY_CELL_DATA_WIDE, &wide);
              is_wide = wide == GHOSTTY_CELL_WIDE_WIDE;
              /* Wide cells (CJK, emoji) get a run of their own, never merged. */
              if (run.text != NULL && !is_wide && !run.wide && run.x + run.n == x
                  && rgba_equal (&run.fg, &fg) && run.bold == bold && run.italic == italic
                  && run.underline == underline && run.strike == strike && run.overline == overline)
                {
                  g_string_append_len (run.text, owned, len);
                  run.n++;
                }
              else
                {
                  close_run (self, row, &run);
                  run = (PendingRun) { x, is_wide ? 2 : 1, fg, bold, italic, is_wide,
                                       underline, strike, overline, g_string_new_len (owned, len) };
                }
            }
        }
      x++;
    }
  close_run (self, row, &run);
  return row;
}

static void
append_rect (GtkSnapshot *snapshot, const GdkRGBA *color, float x, float y, float w, float h)
{
  if (w <= 0 || h <= 0)
    return;
  gtk_snapshot_append_color (snapshot, color, &GRAPHENE_RECT_INIT (x, y, w, h));
}

static void
draw_box (GtkSnapshot *snapshot, const GtkGhosttyBoxGlyph *glyph, const GdkRGBA *color,
          int x, int y, int w, int h)
{
  if (glyph->kind == GTK_GHOSTTY_BOX_SHADE)
    {
      GdkRGBA shaded = *color;
      shaded.alpha *= glyph->shade;
      append_rect (snapshot, &shaded, x, y, w, h);
    }
  else if (glyph->kind == GTK_GHOSTTY_BOX_RECTS)
    {
      for (int i = 0; i < glyph->n_rects; i++)
        {
          const float *r = glyph->rects[i];
          int x1 = x + (int) (r[0] * w + 0.5f), y1 = y + (int) (r[1] * h + 0.5f);
          int x2 = x + (int) ((r[0] + r[2]) * w + 0.5f), y2 = y + (int) ((r[1] + r[3]) * h + 0.5f);
          append_rect (snapshot, color, x1, y1, x2 - x1, y2 - y1);
        }
    }
  else
    {
      int light = MAX (1, h / 16);
      int cx = x + w / 2, cy = y + h / 2;  /* lines run through these pixels */
      if (glyph->arc)
        {
          /* ╭╮╯╰: a quarter curve from the vertical edge to the horizontal one. */
          float px = cx + (light % 2) / 2.f, py = cy + (light % 2) / 2.f;
          GskPathBuilder *builder = gsk_path_builder_new ();
          GskStroke *stroke = gsk_stroke_new (light);
          GskPath *path;
          gsk_path_builder_move_to (builder, px, glyph->arms[3] ? y + h : y);
          gsk_path_builder_cubic_to (builder, px, py, px, py, glyph->arms[1] ? x + w : x, py);
          path = gsk_path_builder_free_to_path (builder);
          gtk_snapshot_append_stroke (snapshot, path, stroke, color);
          gsk_path_unref (path);
          gsk_stroke_free (stroke);
          return;
        }
      for (int arm = 0; arm < 4; arm++)
        {
          int weight = glyph->arms[arm], t, a;
          if (weight == 0)
            continue;
          t = weight == 1 ? light : 2 * light + 1;
          a = t / 2;
          switch (arm)
            {
            case 0: append_rect (snapshot, color, x, cy - a, cx - x + t - a, t); break;
            case 1: append_rect (snapshot, color, cx - a, cy - a, x + w - cx + a, t); break;
            case 2: append_rect (snapshot, color, cx - a, y, t, cy - y + t - a); break;
            default: append_rect (snapshot, color, cx - a, cy - a, t, y + h - cy + a); break;
            }
        }
    }
}

static void
draw_layout (GtkSnapshot *snapshot, PangoLayout *layout, const GdkRGBA *color, float x, float y, float scale)
{
  gtk_snapshot_save (snapshot);
  gtk_snapshot_translate (snapshot, &GRAPHENE_POINT_INIT (x, y));
  if (scale > 0)
    gtk_snapshot_scale (snapshot, scale, 1);
  gtk_snapshot_append_layout (snapshot, layout, color);
  gtk_snapshot_restore (snapshot);
}

static void
draw_cursor (GtkGhosttyTerminal *self, GtkSnapshot *snapshot, const GhosttyRenderStateColors *colors,
             const GdkRGBA *fg_default, const GdkRGBA *bg_default)
{
  GhosttyRenderStateCursor cursor = GHOSTTY_INIT_SIZED (GhosttyRenderStateCursor);
  GdkRGBA color;
  int cw = self->cell_width, ch = self->cell_height, x, y;

  if (ghostty_render_state_get (self->render_state, GHOSTTY_RENDER_STATE_DATA_CURSOR, &cursor) != GHOSTTY_SUCCESS
      || !cursor.visible || !cursor.viewport_has_value)
    return;
  x = cursor.viewport_x - (cursor.wide_tail ? 1 : 0);
  y = cursor.viewport_y;
  if ((guint) y >= self->row_cache->len)
    return;
  color = colors->cursor_has_value ? rgba (colors->cursor) : *fg_default;

  if (cursor.visual_style == GHOSTTY_CURSOR_STYLE_BAR)
    append_rect (snapshot, &color, x * cw, y * ch, 2, ch);
  else if (cursor.visual_style == GHOSTTY_CURSOR_STYLE_UNDERLINE)
    append_rect (snapshot, &color, x * cw, (y + 1) * ch - 2, cw, 2);
  else if (cursor.visual_style == GHOSTTY_CURSOR_STYLE_BLOCK_HOLLOW || !self->focused)
    {
      append_rect (snapshot, &color, x * cw, y * ch, cw, 1);
      append_rect (snapshot, &color, x * cw, (y + 1) * ch - 1, cw, 1);
      append_rect (snapshot, &color, x * cw, y * ch, 1, ch);
      append_rect (snapshot, &color, (x + 1) * cw - 1, y * ch, 1, ch);
    }
  else
    {
      /* Block: fill the cell, then the character on top in the background colour. */
      Row *row = g_ptr_array_index (self->row_cache, y);
      append_rect (snapshot, &color, x * cw, y * ch, cw, ch);
      if ((guint) x < row->chars->len)
        {
          const char *text = g_ptr_array_index (row->chars, x);
          const GtkGhosttyBoxGlyph *glyph = text[0] ? gtk_ghostty_box_glyph (g_utf8_get_char (text)) : NULL;
          if (glyph != NULL)
            draw_box (snapshot, glyph, bg_default, x * cw, y * ch, cw, ch);
          else if (text[0])
            {
              PangoLayout *layout = pango_layout_new (gtk_widget_get_pango_context (GTK_WIDGET (self)));
              pango_layout_set_font_description (layout, self->fonts[0][0]);
              pango_layout_set_text (layout, text, -1);
              draw_layout (snapshot, layout, bg_default, x * cw, y * ch, 0);
              g_object_unref (layout);
            }
        }
    }
}

static void
gtk_ghostty_terminal_snapshot (GtkWidget *widget, GtkSnapshot *snapshot)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (widget);
  GhosttyRenderStateColors colors = GHOSTTY_INIT_SIZED (GhosttyRenderStateColors);
  GhosttyRenderStateDirty dirty = GHOSTTY_RENDER_STATE_DIRTY_FULL;
  GdkRGBA fg, bg;
  int cw, ch;
  guint y = 0;

  ensure_metrics (self);
  cw = self->cell_width;
  ch = self->cell_height;

  ghostty_render_state_update (self->render_state, self->terminal);
  ghostty_render_state_get (self->render_state, GHOSTTY_RENDER_STATE_DATA_COLORS, &colors);
  ghostty_render_state_get (self->render_state, GHOSTTY_RENDER_STATE_DATA_DIRTY, &dirty);
  fg = rgba (colors.foreground);
  bg = rgba (colors.background);

  /* Rebuild only dirty rows; Pango shaping is the expensive part, and on
   * Windows font fallback makes it far more so. */
  ghostty_render_state_get (self->render_state, GHOSTTY_RENDER_STATE_DATA_ROW_ITERATOR, &self->rows);
  while (ghostty_render_state_row_iterator_next (self->rows))
    {
      bool row_dirty = true;
      ghostty_render_state_row_get (self->rows, GHOSTTY_RENDER_STATE_ROW_DATA_DIRTY, &row_dirty);
      if (y >= self->row_cache->len)
        g_ptr_array_add (self->row_cache, build_row (self, &fg, &bg));
      else if (dirty == GHOSTTY_RENDER_STATE_DIRTY_FULL || row_dirty)
        {
          row_free (g_ptr_array_index (self->row_cache, y));
          g_ptr_array_index (self->row_cache, y) = build_row (self, &fg, &bg);
        }
      y++;
    }
  if (y < self->row_cache->len)
    g_ptr_array_set_size (self->row_cache, y);
  ghostty_render_state_clean (self->render_state);

  append_rect (snapshot, &bg, 0, 0, gtk_widget_get_width (widget), gtk_widget_get_height (widget));

  for (y = 0; y < self->row_cache->len; y++)
    {
      Row *row = g_ptr_array_index (self->row_cache, y);
      for (guint i = 0; i < row->bgs->len; i++)
        {
          Span *span = &g_array_index (row->bgs, Span, i);
          append_rect (snapshot, &span->color, span->x * cw, y * ch, span->n * cw, ch);
        }
    }
  for (y = 0; y < self->row_cache->len; y++)
    {
      Row *row = g_ptr_array_index (self->row_cache, y);
      for (guint i = 0; i < row->boxes->len; i++)
        {
          BoxCell *box = &g_array_index (row->boxes, BoxCell, i);
          draw_box (snapshot, gtk_ghostty_box_glyph (box->c), &box->fg, box->x * cw, y * ch, cw, ch);
        }
      for (guint i = 0; i < row->runs->len; i++)
        {
          Run *run = &g_array_index (row->runs, Run, i);
          draw_layout (snapshot, run->layout, &run->fg, run->x * cw, y * ch, run->scale);
          if (run->underline)
            append_rect (snapshot, &run->fg, run->x * cw, y * ch + self->ascent + 2, run->n * cw, 1);
          if (run->strike)
            append_rect (snapshot, &run->fg, run->x * cw, y * ch + ch / 2, run->n * cw, 1);
          if (run->overline)
            append_rect (snapshot, &run->fg, run->x * cw, y * ch + 1, run->n * cw, 1);
        }
    }
  draw_cursor (self, snapshot, &colors, &fg, &bg);
}

/* ---------------------------------------------------------------- input */

static GhosttyMods
mods_from_state (GdkModifierType state)
{
  GhosttyMods mods = 0;
  if (state & GDK_SHIFT_MASK)
    mods |= GHOSTTY_MODS_SHIFT;
  if (state & GDK_CONTROL_MASK)
    mods |= GHOSTTY_MODS_CTRL;
  if (state & GDK_ALT_MASK)
    mods |= GHOSTTY_MODS_ALT;
  if (state & GDK_SUPER_MASK)
    mods |= GHOSTTY_MODS_SUPER;
  if (state & GDK_LOCK_MASK)
    mods |= GHOSTTY_MODS_CAPS_LOCK;
  return mods;
}

static gboolean
is_modifier_key (guint keyval)
{
  switch (keyval)
    {
    case GDK_KEY_Shift_L: case GDK_KEY_Shift_R: case GDK_KEY_Control_L: case GDK_KEY_Control_R:
    case GDK_KEY_Alt_L: case GDK_KEY_Alt_R: case GDK_KEY_Meta_L: case GDK_KEY_Meta_R:
    case GDK_KEY_Super_L: case GDK_KEY_Super_R: case GDK_KEY_Hyper_L: case GDK_KEY_Hyper_R:
    case GDK_KEY_ISO_Level3_Shift: case GDK_KEY_Caps_Lock: case GDK_KEY_Num_Lock: case GDK_KEY_Scroll_Lock:
      return TRUE;
    default:
      return FALSE;
    }
}

/* The keyval of the physical key without modifiers (kitty's unshifted codepoint). */
static guint
base_keyval (GtkEventController *controller, guint keycode, guint keyval)
{
  GdkEvent *event = gtk_event_controller_get_current_event (controller);
  GdkDisplay *display = gtk_widget_get_display (gtk_event_controller_get_widget (controller));
  guint base = 0;
  int group = event != NULL ? (int) gdk_key_event_get_layout (event) : 0;
  if (keycode != 0 && gdk_display_translate_key (display, keycode, 0, group, &base, NULL, NULL, NULL))
    return base;
  return gdk_keyval_to_lower (keyval);
}

static gboolean
on_key_pressed (GtkEventControllerKey *controller, guint keyval, guint keycode,
                GdkModifierType state, GtkGhosttyTerminal *self)
{
  GhosttyKeyEvent event = NULL;
  GhosttyKey key;
  GhosttyMods mods;
  gunichar text = 0, unshifted;
  char utf8[8];
  int utf8_len = 0;
  uint8_t buf[128];
  size_t written = 0;
  GhosttyResult result;

  if (is_modifier_key (keyval))
    return FALSE;

  key = gtk_ghostty_key_from_name (gdk_keyval_name (keyval));
  mods = mods_from_state (state);
  text = gdk_keyval_to_unicode (keyval);
  if (text < 0x20 || text == 0x7f)
    text = 0;  /* control characters are the encoder's job */
  /* Windows reports AltGr as Ctrl+Alt: AltGr+Q on a German layout is "@",
   * which must reach the program as text, not as Ctrl+Alt+@. */
  if ((mods & GHOSTTY_MODS_CTRL) && (mods & GHOSTTY_MODS_ALT) && text != 0
      && !g_unichar_isalpha (text) && g_unichar_isprint (text))
    mods &= ~(GHOSTTY_MODS_CTRL | GHOSTTY_MODS_ALT);
  if (key == GHOSTTY_KEY_UNIDENTIFIED && text == 0)
    return FALSE;
  if (text != 0)
    utf8_len = g_unichar_to_utf8 (text, utf8);
  unshifted = gdk_keyval_to_unicode (base_keyval (GTK_EVENT_CONTROLLER (controller), keycode, keyval));

  if (ghostty_key_event_new (NULL, &event) != GHOSTTY_SUCCESS)
    return FALSE;
  ghostty_key_event_set_action (event, GHOSTTY_KEY_ACTION_PRESS);
  ghostty_key_event_set_key (event, key);
  ghostty_key_event_set_mods (event, mods);
  /* Shift produced the text ('A', '!'): consumed, or kitty sends CSI 97;2u. */
  ghostty_key_event_set_consumed_mods (event, text != 0 ? (mods & GHOSTTY_MODS_SHIFT) : 0);
  if (unshifted >= 0x20)
    ghostty_key_event_set_unshifted_codepoint (event, unshifted);
  if (utf8_len > 0)
    ghostty_key_event_set_utf8 (event, (GhosttyString) { (const uint8_t *) utf8, (size_t) utf8_len });

  ghostty_key_encoder_set_from_terminal (self->key_encoder, self->terminal);
  if (self->legacy_keyboard)
    {
      /* ConPTY forwards a program's kitty request but cannot parse kitty keys. */
      GhosttyKittyKeyFlags flags = GHOSTTY_KITTY_KEY_DISABLED;
      ghostty_key_encoder_set (self->key_encoder, GHOSTTY_KEY_ENCODER_OPT_KITTY_FLAGS, &flags);
    }
  result = ghostty_key_encoder_encode (self->key_encoder, event, buf, sizeof buf, &written);
  if (result == GHOSTTY_SUCCESS)
    emit_input (self, buf, written);
  else if (result == GHOSTTY_OUT_OF_SPACE)
    {
      g_autofree uint8_t *big = g_malloc (written);
      if (ghostty_key_encoder_encode (self->key_encoder, event, big, written, &written) == GHOSTTY_SUCCESS)
        emit_input (self, big, written);
    }
  ghostty_key_event_free (event);
  return TRUE;
}

static void
on_im_commit (GtkIMContext *im, const char *text, GtkGhosttyTerminal *self)
{
  emit_input (self, (const guint8 *) text, strlen (text));
}

static void
send_focus (GtkGhosttyTerminal *self, GhosttyFocusEvent event)
{
  GhosttyTerminalModeConfig mode = { ghostty_mode_new (1004, false), false };
  uint8_t buf[8];
  size_t written = 0;
  if (ghostty_terminal_get (self->terminal, GHOSTTY_TERMINAL_DATA_MODE, &mode) != GHOSTTY_SUCCESS || !mode.value)
    return;
  if (ghostty_focus_encode (event, buf, sizeof buf, &written) == GHOSTTY_SUCCESS)
    emit_input (self, buf, written);
}

static void
on_focus_enter (GtkEventControllerFocus *controller, GtkGhosttyTerminal *self)
{
  self->focused = TRUE;
  gtk_im_context_focus_in (self->im);
  send_focus (self, GHOSTTY_FOCUS_GAINED);
  gtk_widget_queue_draw (GTK_WIDGET (self));
}

static void
on_focus_leave (GtkEventControllerFocus *controller, GtkGhosttyTerminal *self)
{
  self->focused = FALSE;
  gtk_im_context_focus_out (self->im);
  send_focus (self, GHOSTTY_FOCUS_LOST);
  gtk_widget_queue_draw (GTK_WIDGET (self));
}

static void
on_click_pressed (GtkGestureClick *gesture, int n_press, double x, double y, GtkGhosttyTerminal *self)
{
  gtk_widget_grab_focus (GTK_WIDGET (self));
}

/* ------------------------------------------------------------ public API */

/**
 * gtk_ghostty_terminal_new:
 *
 * Returns: (transfer floating): a new terminal view
 */
GtkWidget *
gtk_ghostty_terminal_new (void)
{
  return g_object_new (GTK_GHOSTTY_TYPE_TERMINAL, NULL);
}

/**
 * gtk_ghostty_terminal_feed_data:
 * @self: the terminal
 * @data: (array length=length): bytes the program wrote
 * @length: number of bytes
 *
 * Feeds program output into the terminal. Replies the terminal generates
 * are emitted as #GtkGhosttyTerminal::reply after the bytes are processed.
 */
void
gtk_ghostty_terminal_feed_data (GtkGhosttyTerminal *self, const guint8 *data, gsize length)
{
  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  if (length == 0)
    return;
  ghostty_terminal_vt_write (self->terminal, data, length);
  flush_effects (self);
  gtk_widget_queue_draw (GTK_WIDGET (self));
}

/**
 * gtk_ghostty_terminal_feed:
 * @self: the terminal
 * @data: bytes the program wrote
 */
void
gtk_ghostty_terminal_feed (GtkGhosttyTerminal *self, GBytes *data)
{
  gsize length = 0;
  const guint8 *bytes;
  g_return_if_fail (data != NULL);
  bytes = g_bytes_get_data (data, &length);
  gtk_ghostty_terminal_feed_data (self, bytes, length);
}

/**
 * gtk_ghostty_terminal_paste_text:
 * @self: the terminal
 * @text: UTF-8 text to paste
 *
 * Emits @text as input, with control bytes replaced and framed for
 * bracketed paste when the program asked for it. Whether to confirm an
 * unsafe paste first (see gtk_ghostty_terminal_paste_is_safe()) is up to
 * the caller.
 */
void
gtk_ghostty_terminal_paste_text (GtkGhosttyTerminal *self, const char *text)
{
  GhosttyTerminalModeConfig mode = { ghostty_mode_new (2004, false), false };
  g_autofree char *copy = NULL;
  g_autofree uint8_t *buf = NULL;
  size_t length, needed = 0;

  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  g_return_if_fail (text != NULL);
  length = strlen (text);
  if (length == 0)
    return;
  ghostty_terminal_get (self->terminal, GHOSTTY_TERMINAL_DATA_MODE, &mode);
  copy = g_memdup2 (text, length);  /* encoded in place */
  if (ghostty_paste_encode (copy, length, mode.value, NULL, 0, &needed) != GHOSTTY_OUT_OF_SPACE)
    return;
  buf = g_malloc (needed);
  if (ghostty_paste_encode (copy, length, mode.value, buf, needed, &needed) == GHOSTTY_SUCCESS)
    emit_input (self, buf, needed);
}

/**
 * gtk_ghostty_terminal_paste_is_safe:
 * @text: UTF-8 text
 *
 * Returns: %FALSE when @text could run commands on its own (newlines,
 *   or an attempt to end bracketed paste early)
 */
gboolean
gtk_ghostty_terminal_paste_is_safe (const char *text)
{
  g_return_val_if_fail (text != NULL, TRUE);
  return ghostty_paste_is_safe (text, strlen (text));
}

/**
 * gtk_ghostty_terminal_get_text:
 * @self: the terminal
 *
 * Returns: (transfer full): the visible screen as plain text
 */
char *
gtk_ghostty_terminal_get_text (GtkGhosttyTerminal *self)
{
  GhosttyFormatter formatter = NULL;
  uint8_t *ptr = NULL;
  size_t len = 0;
  char *text;

  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), NULL);
  if (ghostty_formatter_terminal_new (NULL, &formatter, self->terminal) != GHOSTTY_SUCCESS)
    return g_strdup ("");
  if (ghostty_formatter_format_alloc (formatter, NULL, &ptr, &len) != GHOSTTY_SUCCESS)
    {
      ghostty_formatter_free (formatter);
      return g_strdup ("");
    }
  text = g_strndup ((const char *) ptr, len);
  ghostty_free (NULL, ptr, len);
  ghostty_formatter_free (formatter);
  return text;
}

guint
gtk_ghostty_terminal_get_columns (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), 0);
  return self->columns;
}

guint
gtk_ghostty_terminal_get_rows (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), 0);
  return self->n_rows;
}

/**
 * gtk_ghostty_terminal_set_grid_size:
 * @self: the terminal
 * @columns: columns
 * @rows: rows
 *
 * Resizes the terminal grid. A widget that gets allocated sets its own size
 * from the allocation; this is for terminals that are not shown (tests,
 * headless use) or before the first allocation.
 */
void
gtk_ghostty_terminal_set_grid_size (GtkGhosttyTerminal *self, guint columns, guint rows)
{
  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  ensure_metrics (self);
  apply_grid_size (self, columns, rows);
}

const char *
gtk_ghostty_terminal_get_title (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), NULL);
  return self->title;
}

void
gtk_ghostty_terminal_set_font_desc (GtkGhosttyTerminal *self, const PangoFontDescription *font_desc)
{
  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  g_clear_pointer (&self->font, pango_font_description_free);
  self->font = font_desc != NULL ? pango_font_description_copy (font_desc)
                                 : pango_font_description_from_string (DEFAULT_FONT);
  if (pango_font_description_get_size (self->font) == 0)
    pango_font_description_set_size (self->font, 11 * PANGO_SCALE);
  self->metrics_valid = FALSE;
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_FONT_DESC]);
  gtk_widget_queue_resize (GTK_WIDGET (self));
}

/**
 * gtk_ghostty_terminal_get_font_desc:
 * @self: the terminal
 *
 * Returns: (transfer full): the font
 */
PangoFontDescription *
gtk_ghostty_terminal_get_font_desc (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), NULL);
  return pango_font_description_copy (self->font);
}

gboolean
gtk_ghostty_terminal_get_legacy_keyboard (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), FALSE);
  return self->legacy_keyboard;
}

/**
 * gtk_ghostty_terminal_set_legacy_keyboard:
 * @self: the terminal
 * @legacy: whether to ignore the kitty keyboard protocol
 *
 * Set this when the byte stream goes through Windows ConPTY: it forwards a
 * program's kitty keyboard request but cannot parse kitty-encoded keys.
 */
void
gtk_ghostty_terminal_set_legacy_keyboard (GtkGhosttyTerminal *self, gboolean legacy)
{
  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  legacy = !!legacy;
  if (self->legacy_keyboard == legacy)
    return;
  self->legacy_keyboard = legacy;
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_LEGACY_KEYBOARD]);
}

gboolean
gtk_ghostty_terminal_get_pull_history_on_grow (GtkGhosttyTerminal *self)
{
  g_return_val_if_fail (GTK_GHOSTTY_IS_TERMINAL (self), TRUE);
  return self->pull_history_on_grow;
}

/**
 * gtk_ghostty_terminal_set_pull_history_on_grow:
 * @self: the terminal
 * @pull: whether growing the terminal brings scrollback rows back
 *
 * Turn this off when the program side keeps its own screen without
 * scrollback and repaints it after a resize (Windows ConPTY).
 */
void
gtk_ghostty_terminal_set_pull_history_on_grow (GtkGhosttyTerminal *self, gboolean pull)
{
  bool value;
  g_return_if_fail (GTK_GHOSTTY_IS_TERMINAL (self));
  pull = !!pull;
  if (self->pull_history_on_grow == pull)
    return;
  self->pull_history_on_grow = pull;
  value = pull;
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_RESIZE_PULL_SCROLLBACK, &value);
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_PULL_HISTORY_ON_GROW]);
}

/* -------------------------------------------------------------- GObject */

static void
gtk_ghostty_terminal_get_property (GObject *object, guint prop_id, GValue *value, GParamSpec *pspec)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (object);
  switch (prop_id)
    {
    case PROP_COLUMNS: g_value_set_uint (value, self->columns); break;
    case PROP_ROWS: g_value_set_uint (value, self->n_rows); break;
    case PROP_TITLE: g_value_set_string (value, self->title); break;
    case PROP_LEGACY_KEYBOARD: g_value_set_boolean (value, self->legacy_keyboard); break;
    case PROP_PULL_HISTORY_ON_GROW: g_value_set_boolean (value, self->pull_history_on_grow); break;
    case PROP_FONT_DESC: g_value_take_boxed (value, pango_font_description_copy (self->font)); break;
    default: G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
    }
}

static void
gtk_ghostty_terminal_set_property (GObject *object, guint prop_id, const GValue *value, GParamSpec *pspec)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (object);
  switch (prop_id)
    {
    case PROP_LEGACY_KEYBOARD: gtk_ghostty_terminal_set_legacy_keyboard (self, g_value_get_boolean (value)); break;
    case PROP_PULL_HISTORY_ON_GROW:
      gtk_ghostty_terminal_set_pull_history_on_grow (self, g_value_get_boolean (value));
      break;
    case PROP_FONT_DESC: gtk_ghostty_terminal_set_font_desc (self, g_value_get_boxed (value)); break;
    default: G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
    }
}

static void
gtk_ghostty_terminal_dispose (GObject *object)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (object);
  if (self->im != NULL)
    gtk_im_context_set_client_widget (self->im, NULL);
  g_clear_object (&self->im);
  G_OBJECT_CLASS (gtk_ghostty_terminal_parent_class)->dispose (object);
}

static void
gtk_ghostty_terminal_finalize (GObject *object)
{
  GtkGhosttyTerminal *self = GTK_GHOSTTY_TERMINAL (object);
  g_clear_pointer (&self->row_cache, g_ptr_array_unref);
  ghostty_render_state_row_cells_free (self->cells);
  ghostty_render_state_row_iterator_free (self->rows);
  ghostty_render_state_free (self->render_state);
  ghostty_key_encoder_free (self->key_encoder);
  ghostty_terminal_free (self->terminal);
  g_byte_array_unref (self->pending_reply);
  g_free (self->title);
  g_clear_pointer (&self->font, pango_font_description_free);
  for (int bold = 0; bold < 2; bold++)
    for (int italic = 0; italic < 2; italic++)
      g_clear_pointer (&self->fonts[bold][italic], pango_font_description_free);
  g_clear_pointer (&self->grid_attrs, pango_attr_list_unref);
  G_OBJECT_CLASS (gtk_ghostty_terminal_parent_class)->finalize (object);
}

static void
gtk_ghostty_terminal_class_init (GtkGhosttyTerminalClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GtkWidgetClass *widget_class = GTK_WIDGET_CLASS (klass);

  object_class->get_property = gtk_ghostty_terminal_get_property;
  object_class->set_property = gtk_ghostty_terminal_set_property;
  object_class->dispose = gtk_ghostty_terminal_dispose;
  object_class->finalize = gtk_ghostty_terminal_finalize;
  widget_class->measure = gtk_ghostty_terminal_measure;
  widget_class->size_allocate = gtk_ghostty_terminal_size_allocate;
  widget_class->snapshot = gtk_ghostty_terminal_snapshot;

  properties[PROP_COLUMNS] = g_param_spec_uint ("columns", NULL, NULL, 0, G_MAXUINT16, DEFAULT_COLUMNS,
                                                G_PARAM_READABLE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  properties[PROP_ROWS] = g_param_spec_uint ("rows", NULL, NULL, 0, G_MAXUINT16, DEFAULT_ROWS,
                                             G_PARAM_READABLE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  properties[PROP_TITLE] = g_param_spec_string ("title", NULL, NULL, NULL,
                                                G_PARAM_READABLE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  properties[PROP_LEGACY_KEYBOARD] =
    g_param_spec_boolean ("legacy-keyboard", NULL, NULL, FALSE,
                          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  properties[PROP_PULL_HISTORY_ON_GROW] =
    g_param_spec_boolean ("pull-history-on-grow", NULL, NULL, TRUE,
                          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  properties[PROP_FONT_DESC] =
    g_param_spec_boxed ("font-desc", NULL, NULL, PANGO_TYPE_FONT_DESCRIPTION,
                        G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | G_PARAM_EXPLICIT_NOTIFY);
  g_object_class_install_properties (object_class, N_PROPS, properties);

  /**
   * GtkGhosttyTerminal::input:
   * @self: the terminal
   * @data: bytes to write to the program (keys, committed text, paste, focus)
   */
  signals[SIGNAL_INPUT] = g_signal_new ("input", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST,
                                        0, NULL, NULL, NULL, G_TYPE_NONE, 1, G_TYPE_BYTES);
  /**
   * GtkGhosttyTerminal::reply:
   * @self: the terminal
   * @data: the terminal's answers to the program's queries (DA, DSR, ...)
   *
   * Write these to the program like input. Emitted after the fed bytes are
   * processed, never from inside libghostty-vt.
   */
  signals[SIGNAL_REPLY] = g_signal_new ("reply", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST,
                                        0, NULL, NULL, NULL, G_TYPE_NONE, 1, G_TYPE_BYTES);
  /**
   * GtkGhosttyTerminal::size-changed:
   * @self: the terminal
   * @columns: new number of columns
   * @rows: new number of rows
   * @cell_width: cell width in pixels
   * @cell_height: cell height in pixels
   *
   * Tell the program's PTY (TIOCSWINSZ, ResizePseudoConsole, ssh window-change).
   */
  signals[SIGNAL_SIZE_CHANGED] = g_signal_new ("size-changed", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST,
                                               0, NULL, NULL, NULL, G_TYPE_NONE, 4,
                                               G_TYPE_UINT, G_TYPE_UINT, G_TYPE_UINT, G_TYPE_UINT);
  /**
   * GtkGhosttyTerminal::bell:
   * @self: the terminal
   */
  signals[SIGNAL_BELL] = g_signal_new ("bell", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST,
                                       0, NULL, NULL, NULL, G_TYPE_NONE, 0);

  gtk_widget_class_set_css_name (widget_class, "ghostty-terminal");
  gtk_widget_class_set_accessible_role (widget_class, GTK_ACCESSIBLE_ROLE_TERMINAL);
}

static void
gtk_ghostty_terminal_init (GtkGhosttyTerminal *self)
{
  GtkEventController *keys, *focus;
  GtkGesture *click;
  size_t max_bytes = SIZE_MAX, max_lines = DEFAULT_SCROLLBACK_LINES;

  self->columns = DEFAULT_COLUMNS;
  self->n_rows = DEFAULT_ROWS;
  self->pull_history_on_grow = TRUE;
  self->pending_reply = g_byte_array_new ();
  self->row_cache = g_ptr_array_new_with_free_func (row_free);
  self->font = pango_font_description_from_string (DEFAULT_FONT);

  if (ghostty_terminal_new (NULL, &self->terminal, self->columns, self->n_rows) != GHOSTTY_SUCCESS)
    g_error ("ghostty_terminal_new failed");
  ghostty_render_state_new (NULL, &self->render_state);
  ghostty_render_state_row_iterator_new (NULL, &self->rows);
  ghostty_render_state_row_cells_new (NULL, &self->cells);
  ghostty_key_encoder_new (NULL, &self->key_encoder);

  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_USERDATA, self);
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_WRITE_PTY, (const void *) on_write_pty);
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_BELL, (const void *) on_bell);
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_TITLE_CHANGED, (const void *) on_title_changed);
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_DEVICE_ATTRIBUTES, (const void *) on_device_attributes);
  /* The byte limit defaults to one page (~10 KB): let the line limit decide. */
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_SCROLLBACK_MAX_BYTES, &max_bytes);
  ghostty_terminal_set (self->terminal, GHOSTTY_TERMINAL_OPT_SCROLLBACK_MAX_LINES, &max_lines);

  gtk_widget_set_focusable (GTK_WIDGET (self), TRUE);

  self->im = gtk_im_multicontext_new ();
  gtk_im_context_set_client_widget (self->im, GTK_WIDGET (self));
  g_signal_connect (self->im, "commit", G_CALLBACK (on_im_commit), self);

  keys = gtk_event_controller_key_new ();
  gtk_event_controller_key_set_im_context (GTK_EVENT_CONTROLLER_KEY (keys), self->im);
  g_signal_connect (keys, "key-pressed", G_CALLBACK (on_key_pressed), self);
  gtk_widget_add_controller (GTK_WIDGET (self), keys);

  focus = gtk_event_controller_focus_new ();
  g_signal_connect (focus, "enter", G_CALLBACK (on_focus_enter), self);
  g_signal_connect (focus, "leave", G_CALLBACK (on_focus_leave), self);
  gtk_widget_add_controller (GTK_WIDGET (self), focus);

  click = gtk_gesture_click_new ();
  g_signal_connect (click, "pressed", G_CALLBACK (on_click_pressed), self);
  gtk_widget_add_controller (GTK_WIDGET (self), GTK_EVENT_CONTROLLER (click));
}
