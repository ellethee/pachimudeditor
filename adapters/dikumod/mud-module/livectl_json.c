/*
 * livectl_json.c - parser/serializzatore JSON minimo a limiti fissi (vedi livectl_json.h).
 * Compila con g++ -std=gnu++98 (e come C). Nessuna allocazione dinamica.
 */
#include <string.h>
#include <stdio.h>
#include "livectl_json.h"

struct pctx {
  struct jdoc *d;
  const unsigned char *p, *end;
  const char *err;
};

static int fail(struct pctx *c, const char *e)
{
  if (!c->err)
    c->err = e;
  return -1;
}

static void skip_ws(struct pctx *c)
{
  while (c->p < c->end && (*c->p == ' ' || *c->p == '\t' || *c->p == '\r'))
    c->p++;
}

static int new_node(struct pctx *c, int type)
{
  struct jnode *n;
  if (c->d->count >= LC_MAX_NODES)
    return fail(c, "too_many_values");
  n = &c->d->nodes[c->d->count];
  n->type = type;
  n->i = 0;
  n->s = 0;
  n->key = 0;
  n->first = -1;
  n->next = -1;
  n->n = 0;
  return c->d->count++;
}

static int hexval(int ch)
{
  if (ch >= '0' && ch <= '9')
    return ch - '0';
  if (ch >= 'a' && ch <= 'f')
    return ch - 'a' + 10;
  if (ch >= 'A' && ch <= 'F')
    return ch - 'A' + 10;
  return -1;
}

static int read_hex4(struct pctx *c, unsigned *out)
{
  unsigned v = 0;
  int k, h;
  if (c->end - c->p < 4)
    return fail(c, "bad_escape");
  for (k = 0; k < 4; k++) {
    h = hexval(c->p[k]);
    if (h < 0)
      return fail(c, "bad_escape");
    v = v * 16 + (unsigned)h;
  }
  c->p += 4;
  *out = v;
  return 0;
}

/* scrive il punto di codice cp in UTF-8 su o (almeno 4 byte liberi); ritorna i byte scritti */
static int put_utf8(unsigned cp, unsigned char *o)
{
  if (cp < 0x80) {
    o[0] = (unsigned char)cp;
    return 1;
  }
  if (cp < 0x800) {
    o[0] = (unsigned char)(0xC0 | (cp >> 6));
    o[1] = (unsigned char)(0x80 | (cp & 0x3F));
    return 2;
  }
  if (cp < 0x10000) {
    o[0] = (unsigned char)(0xE0 | (cp >> 12));
    o[1] = (unsigned char)(0x80 | ((cp >> 6) & 0x3F));
    o[2] = (unsigned char)(0x80 | (cp & 0x3F));
    return 3;
  }
  o[0] = (unsigned char)(0xF0 | (cp >> 18));
  o[1] = (unsigned char)(0x80 | ((cp >> 12) & 0x3F));
  o[2] = (unsigned char)(0x80 | ((cp >> 6) & 0x3F));
  o[3] = (unsigned char)(0x80 | (cp & 0x3F));
  return 4;
}

/* lunghezza (2..4) della sequenza UTF-8 valida che inizia a p, 0 se invalida */
static int utf8_seq(const unsigned char *p, const unsigned char *end)
{
  unsigned char b = *p;
  int need;
  if (b >= 0xC2 && b <= 0xDF)
    need = 2;
  else if (b >= 0xE0 && b <= 0xEF)
    need = 3;
  else if (b >= 0xF0 && b <= 0xF4)
    need = 4;
  else
    return 0;
  if (end - p < need)
    return 0;
  for (int k = 1; k < need; k++)
    if ((p[k] & 0xC0) != 0x80)
      return 0;
  if (b == 0xE0 && p[1] < 0xA0)
    return 0;
  if (b == 0xED && p[1] > 0x9F)
    return 0;
  if (b == 0xF0 && p[1] < 0x90)
    return 0;
  if (b == 0xF4 && p[1] > 0x8F)
    return 0;
  return need;
}

/* decodifica una stringa JSON in d->buf; *out punta alla stringa NUL-terminata */
static int parse_string(struct pctx *c, const char **out)
{
  struct jdoc *d = c->d;
  unsigned char *o = (unsigned char *)d->buf + d->used;
  unsigned char *start = o;
  unsigned char *limit = (unsigned char *)d->buf + LC_MAX_LINE - 4;

  if (c->p >= c->end || *c->p != '"')
    return fail(c, "expected_string");
  c->p++;
  for (;;) {
    unsigned char b;
    if (c->p >= c->end)
      return fail(c, "unterminated_string");
    if (o >= limit || (o - start) >= LC_MAX_STR)
      return fail(c, "string_too_long");
    b = *c->p;
    if (b == '"') {
      c->p++;
      break;
    }
    if (b < 0x20)
      return fail(c, "control_char");
    if (b == '\\') {
      unsigned cp, lo;
      c->p++;
      if (c->p >= c->end)
        return fail(c, "bad_escape");
      b = *c->p++;
      switch (b) {
      case '"': *o++ = '"'; break;
      case '\\': *o++ = '\\'; break;
      case '/': *o++ = '/'; break;
      case 'b': *o++ = '\b'; break;
      case 'f': *o++ = '\f'; break;
      case 'n': *o++ = '\n'; break;
      case 'r': *o++ = '\r'; break;
      case 't': *o++ = '\t'; break;
      case 'u':
        if (read_hex4(c, &cp) < 0)
          return -1;
        if (cp >= 0xD800 && cp <= 0xDBFF) {
          if (c->end - c->p < 2 || c->p[0] != '\\' || c->p[1] != 'u')
            return fail(c, "bad_surrogate");
          c->p += 2;
          if (read_hex4(c, &lo) < 0)
            return -1;
          if (lo < 0xDC00 || lo > 0xDFFF)
            return fail(c, "bad_surrogate");
          cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
          return fail(c, "bad_surrogate");
        }
        if (cp == 0)
          return fail(c, "nul_char");
        o += put_utf8(cp, o);
        break;
      default:
        return fail(c, "bad_escape");
      }
    } else if (b < 0x80) {
      *o++ = b;
      c->p++;
    } else {
      int k = utf8_seq(c->p, c->end);
      if (!k)
        return fail(c, "bad_utf8");
      memcpy(o, c->p, (size_t)k);
      o += k;
      c->p += k;
    }
  }
  *o++ = 0;
  d->used = (int)((char *)o - d->buf);
  *out = (const char *)start;
  return 0;
}

static int parse_value(struct pctx *c, int depth);

static int parse_number(struct pctx *c)
{
  int neg = 0, digits = 0, idx;
  long long v = 0;
  idx = new_node(c, J_INT);
  if (idx < 0)
    return -1;
  if (c->p < c->end && *c->p == '-') {
    neg = 1;
    c->p++;
  }
  if (c->p >= c->end || *c->p < '0' || *c->p > '9')
    return fail(c, "bad_number");
  if (*c->p == '0' && c->p + 1 < c->end && c->p[1] >= '0' && c->p[1] <= '9')
    return fail(c, "bad_number");
  while (c->p < c->end && *c->p >= '0' && *c->p <= '9') {
    if (++digits > 18)
      return fail(c, "number_too_big");
    v = v * 10 + (*c->p - '0');
    c->p++;
  }
  if (c->p < c->end && (*c->p == '.' || *c->p == 'e' || *c->p == 'E'))
    return fail(c, "not_integer");
  c->d->nodes[idx].i = neg ? -v : v;
  return idx;
}

static int match_lit(struct pctx *c, const char *lit)
{
  size_t n = strlen(lit);
  if ((size_t)(c->end - c->p) < n || memcmp(c->p, lit, n) != 0)
    return 0;
  c->p += n;
  return 1;
}

static int parse_container(struct pctx *c, int depth, int is_obj)
{
  int idx, last = -1, child;
  char close = is_obj ? '}' : ']';
  int maxn = is_obj ? LC_MAX_KEYS : LC_MAX_ARRAY;
  if (depth > LC_MAX_DEPTH)
    return fail(c, "too_deep");
  idx = new_node(c, is_obj ? J_OBJ : J_ARR);
  if (idx < 0)
    return -1;
  c->p++; /* { o [ */
  skip_ws(c);
  if (c->p < c->end && *c->p == close) {
    c->p++;
    return idx;
  }
  for (;;) {
    const char *key = 0;
    skip_ws(c);
    if (is_obj) {
      if (parse_string(c, &key) < 0)
        return -1;
      skip_ws(c);
      if (c->p >= c->end || *c->p != ':')
        return fail(c, "expected_colon");
      c->p++;
      skip_ws(c);
    }
    if (c->d->nodes[idx].n >= maxn)
      return fail(c, "too_many_items");
    child = parse_value(c, depth + 1);
    if (child < 0)
      return -1;
    if (is_obj) {
      int s;
      for (s = c->d->nodes[idx].first; s >= 0; s = c->d->nodes[s].next)
        if (strcmp(c->d->nodes[s].key, key) == 0)
          return fail(c, "duplicate_key");
      c->d->nodes[child].key = key;
    }
    if (last < 0)
      c->d->nodes[idx].first = child;
    else
      c->d->nodes[last].next = child;
    last = child;
    c->d->nodes[idx].n++;
    skip_ws(c);
    if (c->p >= c->end)
      return fail(c, "unterminated");
    if (*c->p == ',') {
      c->p++;
      continue;
    }
    if (*c->p == close) {
      c->p++;
      return idx;
    }
    return fail(c, "expected_comma");
  }
}

static int parse_value(struct pctx *c, int depth)
{
  int idx;
  skip_ws(c);
  if (c->p >= c->end)
    return fail(c, "unexpected_end");
  switch (*c->p) {
  case '{': return parse_container(c, depth, 1);
  case '[': return parse_container(c, depth, 0);
  case '"':
    idx = new_node(c, J_STR);
    if (idx < 0)
      return -1;
    if (parse_string(c, &c->d->nodes[idx].s) < 0)
      return -1;
    return idx;
  case 't':
  case 'f':
  case 'n':
    if (*c->p == 'n') {
      if (!match_lit(c, "null"))
        return fail(c, "bad_literal");
      return new_node(c, J_NULL);
    }
    idx = new_node(c, J_BOOL);
    if (idx < 0)
      return -1;
    if (*c->p == 't') {
      if (!match_lit(c, "true"))
        return fail(c, "bad_literal");
      c->d->nodes[idx].i = 1;
    } else if (!match_lit(c, "false")) {
      return fail(c, "bad_literal");
    }
    return idx;
  default:
    if (*c->p == '-' || (*c->p >= '0' && *c->p <= '9'))
      return parse_number(c);
    return fail(c, "unexpected_char");
  }
}

int json_parse(struct jdoc *d, const char *line, int len, const char **err)
{
  struct pctx c;
  c.d = d;
  c.err = 0;
  d->count = 0;
  d->used = 0;
  if (len < 0 || len > LC_MAX_LINE || memchr(line, 0, (size_t)len)) {
    *err = len > LC_MAX_LINE ? "line_too_long" : "bad_input";
    return -1;
  }
  c.p = (const unsigned char *)line;
  c.end = c.p + len;
  if (parse_value(&c, 1) < 0) {
    *err = c.err ? c.err : "parse_error";
    return -1;
  }
  skip_ws(&c);
  if (c.p != c.end) {
    *err = "trailing_data";
    return -1;
  }
  return 0;
}

const struct jnode *json_child(const struct jdoc *d, const struct jnode *n)
{
  return n && n->first >= 0 ? &d->nodes[n->first] : 0;
}

const struct jnode *json_next(const struct jdoc *d, const struct jnode *n)
{
  return n && n->next >= 0 ? &d->nodes[n->next] : 0;
}

const struct jnode *json_get(const struct jdoc *d, const struct jnode *obj, const char *key)
{
  const struct jnode *c;
  if (!obj || obj->type != J_OBJ)
    return 0;
  for (c = json_child(d, obj); c; c = json_next(d, c))
    if (c->key && strcmp(c->key, key) == 0)
      return c;
  return 0;
}

/* ---- scrittura ---- */

void jw_init(struct jw *w, char *buf, int cap)
{
  w->p = buf;
  w->len = 0;
  w->cap = cap;
  w->over = 0;
  if (cap > 0)
    buf[0] = 0;
}

void jw_char(struct jw *w, char ch)
{
  if (w->over)
    return;
  if (w->len + 1 >= w->cap) {
    w->over = 1;
    return;
  }
  w->p[w->len++] = ch;
  w->p[w->len] = 0;
}

void jw_raw(struct jw *w, const char *s)
{
  while (*s)
    jw_char(w, *s++);
}

void jw_int(struct jw *w, long long v)
{
  char tmp[32];
  snprintf(tmp, sizeof tmp, "%lld", v);
  jw_raw(w, tmp);
}

static void jw_esc(struct jw *w, unsigned char b)
{
  char tmp[8];
  if (b == '"' || b == '\\') {
    jw_char(w, '\\');
    jw_char(w, (char)b);
  } else if (b < 0x20) {
    snprintf(tmp, sizeof tmp, "\\u%04x", b);
    jw_raw(w, tmp);
  } else {
    jw_char(w, (char)b);
  }
}

void jw_str(struct jw *w, const char *s)
{
  jw_char(w, '"');
  for (; s && *s; s++)
    jw_esc(w, (unsigned char)*s);
  jw_char(w, '"');
}

void jw_str_latin1(struct jw *w, const char *s)
{
  jw_char(w, '"');
  for (; s && *s; s++) {
    unsigned char b = (unsigned char)*s;
    if (b >= 0x80) {
      jw_char(w, (char)(0xC0 | (b >> 6)));
      jw_char(w, (char)(0x80 | (b & 0x3F)));
    } else {
      jw_esc(w, b);
    }
  }
  jw_char(w, '"');
}

int utf8_to_latin1(const char *in, char *out, int cap)
{
  const unsigned char *p = (const unsigned char *)in;
  const unsigned char *end = p + strlen(in);
  int n = 0;
  while (p < end) {
    unsigned cp;
    if (*p < 0x80) {
      cp = *p++;
    } else {
      int k = utf8_seq(p, end);
      if (k != 2)
        return -1; /* sequenze di 3-4 byte sono sempre oltre U+00FF */
      cp = ((unsigned)(p[0] & 0x1F) << 6) | (p[1] & 0x3F);
      p += 2;
      if (cp > 0xFF)
        return -1;
    }
    if (n + 1 >= cap)
      return -2;
    out[n++] = (char)cp;
  }
  out[n] = 0;
  return n;
}
