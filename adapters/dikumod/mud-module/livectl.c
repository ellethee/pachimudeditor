/*
 * livectl.c - canale di controllo live per Diku Modificato (DikuMod1), protocollo livectl v1.
 *
 * Un solo thread (quello del gioco): livectl_poll() gira in coda a ogni iterazione di game_loop(), non blocca mai,
 * non prende lock e non alloca memoria in funzione dell'input. Tutta la configurazione e' nell'ambiente
 * (LIVECTL_SOCKET, LIVECTL_TOKEN, LIVECTL_CLASSES, ...): vedi README.
 * Compilato solo con -DLIVECTL; senza il flag le funzioni sono vuote.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <time.h>
#include <stdarg.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <sys/un.h>

#include "protos.h"
#include "version.h"
#include "livectl.h"

#ifndef LIVECTL

void livectl_init(void) {}
void livectl_poll(void) {}
void livectl_shutdown(void) {}

#else

#include "livectl_json.h"

#define LC_VERSION       "livectl 0.1"
#define LC_PROTOCOL      1
#define LC_MAX_CONNS     8
#define LC_IN_SIZE       (4 * (LC_MAX_LINE + 2))
#define LC_MAX_RESP      65536
#define LC_OUT_SIZE      (2 * LC_MAX_RESP)
#define LC_MAX_TEXT      400
#define LC_MAX_PENDING   8
#define LC_MAX_PER_TICK  16
#define LC_TICK_BUDGET_US 5000
#define LC_HELLO_TIMEOUT_MS 5000
#define LC_IDLE_TIMEOUT_MS  300000
#define LC_RATE_CONN     20     /* richieste al secondo per connessione */
#define LC_RATE_GLOBAL   50
#define LC_MAX_DENY      32
#define LC_TOKEN_MIN     32
#define LC_TOKEN_MAX     200

extern struct descriptor_data *descriptor_list;
extern struct char_data *character_list;
extern struct zone_data *zone_table;
extern int top_of_zone_table, top_of_mobt, top_of_objt;
extern long Uptime;
extern int pulse;
extern struct reset_q_type gReset_q;
extern struct index_data *obj_index;
long GetLagIndex(void);

/* ---------------------------------------------------------------- stato */

struct bucket {
  long long last_ms;
  long tokens; /* millesimi di richiesta */
};

struct conn {
  int fd;
  int authed, fails, close_after;
  int id, uid, pid;
  long long accepted_ms, last_ms;
  struct bucket rate;
  int inlen, outlen, outoff;
  char actor[68];
  char in[LC_IN_SIZE];
  char out[LC_OUT_SIZE];
};

struct denyrange {
  long lo, hi;
};

static struct {
  int active;
  int listen_fd;
  int owns_socket;
  int write_enabled;
  int max_conn;
  int audit_fd;
  int next_conn_id;
  char sock_path[108];
  char token[LC_TOKEN_MAX + 1];
  int toklen;
  int allow_uid;
  int ndeny;
  struct denyrange deny[LC_MAX_DENY];
  long long ticks;
  long long lock_until_ms;
  long long fail_window_start_ms;
  int fail_window_count;
  struct bucket global;
  struct conn conns[LC_MAX_CONNS];
} L;

static struct jdoc g_doc;
static char g_result[LC_MAX_RESP];
static char g_resp[LC_MAX_RESP];

/* errore corrente (impostato dai gestori) */
static char g_code[40], g_msg[160], g_eparams[200];
/* contesto dell'audit del comando in corso */
static char g_target[80], g_extra[200];

static const char *CLASS_NAMES[11] = {"magic_user", "cleric", "warrior", "thief", "druid", "monk",
                                      "barbarian", "sorcerer", "paladin", "ranger", "psi"};

/* ---------------------------------------------------------------- utilita' */

static long long now_ms(void)
{
  struct timeval tv;
  gettimeofday(&tv, 0);
  return (long long)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

static long long now_us(void)
{
  struct timeval tv;
  gettimeofday(&tv, 0);
  return (long long)tv.tv_sec * 1000000 + tv.tv_usec;
}

static void glog(const char *fmt, ...)
{
  char buf[300];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);
  mudlog(LOG_CHECK, (char *)"livectl: %s", buf);
}

static int E(const char *code, const char *msg)
{
  snprintf(g_code, sizeof g_code, "%s", code);
  snprintf(g_msg, sizeof g_msg, "%s", msg);
  g_eparams[0] = 0;
  return -1;
}

static int EP(const char *code, const char *msg, const char *fmt, ...)
{
  va_list ap;
  E(code, msg);
  va_start(ap, fmt);
  vsnprintf(g_eparams, sizeof g_eparams, fmt, ap);
  va_end(ap);
  return -1;
}

static void set_target(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(g_target, sizeof g_target, fmt, ap);
  va_end(ap);
}

static void add_extra(const char *fmt, ...)
{
  size_t n = strlen(g_extra);
  va_list ap;
  if (n >= sizeof g_extra - 2)
    return;
  va_start(ap, fmt);
  vsnprintf(g_extra + n, sizeof g_extra - n, fmt, ap);
  va_end(ap);
}

/* confronto a tempo costante (indipendente dal contenuto, dalla posizione della prima differenza e dalle lunghezze fino a 256) */
static int token_equal(const char *a, int la, const char *b, int lb)
{
  unsigned diff = (unsigned)(la ^ lb);
  for (int i = 0; i < 256; i++) {
    unsigned char ca = i < la ? (unsigned char)a[i] : 0;
    unsigned char cb = i < lb ? (unsigned char)b[i] : 0;
    diff |= (unsigned)(ca ^ cb);
  }
  return diff == 0;
}

static int take(struct bucket *b, int per_sec, long long now)
{
  long cap = per_sec * 1000L;
  if (b->last_ms == 0) {
    b->last_ms = now;
    b->tokens = cap;
  }
  if (now > b->last_ms) {
    long long add = (now - b->last_ms) * per_sec;
    b->tokens = (long)(b->tokens + add > cap ? cap : b->tokens + add);
    b->last_ms = now;
  }
  if (b->tokens < 1000)
    return 0;
  b->tokens -= 1000;
  return 1;
}

static int valid_name(const char *s)
{
  int n = 0;
  if (!isalpha((unsigned char)s[0]))
    return 0;
  for (; s[n]; n++)
    if (n >= 20 || !(isalnum((unsigned char)s[n]) || s[n] == '_' || s[n] == '-'))
      return 0;
  return n > 0;
}

static void sanitize(char *dst, size_t cap, const char *src, int allow_space)
{
  size_t i = 0;
  for (; src && *src && i + 1 < cap; src++) {
    unsigned char c = (unsigned char)*src;
    dst[i++] = (isalnum(c) || strchr("._:@/-,=>", c) || (allow_space && c == ' ')) ? (char)c : '_';
  }
  dst[i] = 0;
}

/* ---------------------------------------------------------------- audit */

static void audit(struct conn *c, const char *cmd, const char *result)
{
  char line[600], ts[40], actor[80], target[100], extra[240], code[60];
  time_t t = time(0);
  struct tm tmv;
  int n;
  if (L.audit_fd < 0)
    return;
  localtime_r(&t, &tmv);
  strftime(ts, sizeof ts, "%Y-%m-%dT%H:%M:%S%z", &tmv);
  sanitize(actor, sizeof actor, c->actor[0] ? c->actor : "-", 0);
  sanitize(target, sizeof target, g_target[0] ? g_target : "-", 0);
  sanitize(extra, sizeof extra, g_extra, 1);
  sanitize(code, sizeof code, result, 0);
  n = snprintf(line, sizeof line, "%s conn=%d uid=%d pid=%d actor=%s cmd=%s target=%s result=%s%s%s\n", ts, c->id, c->uid,
               c->pid, actor, cmd, target, code, extra[0] ? " " : "", extra);
  if (n > (int)sizeof line - 1)
    n = (int)sizeof line - 1;
  if (write(L.audit_fd, line, (size_t)n) < 0)
    glog("scrittura audit fallita (%s)", strerror(errno));
}

/* ---------------------------------------------------------------- giocatori */

static int char_ok(struct char_data *ch)
{
  return ch && ch->nMagicNumber == CHAR_VALID_MAGIC;
}

/* cerca un giocatore connesso e in gioco; ch = personaggio vero (original se trasformato), body = personaggio attivo */
static int find_player(const char *name, struct descriptor_data **dp, struct char_data **chp)
{
  struct descriptor_data *d;
  struct char_data *p;
  if (!valid_name(name))
    return EP("bad_params", "nome non valido", "{\"field\":\"name\"}");
  for (d = descriptor_list; d; d = d->next) {
    struct char_data *ch = d->original ? d->original : d->character;
    if (!ch || !char_ok(ch) || !ch->player.name)
      continue;
    if (strcasecmp(ch->player.name, name) == 0) {
      if (d->connected != CON_PLYNG || !char_ok(d->character))
        return E("player_not_playing", "il giocatore non e' in gioco");
      *dp = d;
      *chp = ch;
      return 0;
    }
  }
  for (p = character_list; p; p = p->next)
    if (char_ok(p) && !IS_NPC(p) && !p->desc && p->player.name && strcasecmp(p->player.name, name) == 0)
      return E("player_not_playing", "il giocatore ha il collegamento caduto");
  return EP("not_found", "giocatore non connesso", "{\"what\":\"player\"}");
}

static int writable_player(struct descriptor_data *d)
{
  if (d->original || d->str || d->showstr_point)
    return E("player_busy", "il giocatore e' trasformato o sta scrivendo un testo");
  return 0;
}

/* ---------------------------------------------------------------- parametri */

static int p_int(const struct jdoc *doc, const struct jnode *obj, const char *k, int required, long long *out)
{
  const struct jnode *n = json_get(doc, obj, k);
  if (!n) {
    if (required)
      return EP("bad_params", "parametro mancante", "{\"field\":\"%s\"}", k);
    return 0;
  }
  if (n->type != J_INT)
    return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", k);
  *out = n->i;
  return 1;
}

static int p_bool(const struct jdoc *doc, const struct jnode *obj, const char *k, int *out)
{
  const struct jnode *n = json_get(doc, obj, k);
  if (!n)
    return 0;
  if (n->type != J_BOOL)
    return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", k);
  *out = (int)n->i;
  return 1;
}

static int p_str(const struct jdoc *doc, const struct jnode *obj, const char *k, int required, const char **out)
{
  const struct jnode *n = json_get(doc, obj, k);
  if (!n) {
    if (required)
      return EP("bad_params", "parametro mancante", "{\"field\":\"%s\"}", k);
    return 0;
  }
  if (n->type != J_STR)
    return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", k);
  *out = n->s;
  return 1;
}

/* solo le chiavi elencate (terminate da NULL) sono ammesse */
static int check_keys(const struct jdoc *doc, const struct jnode *obj, const char *const *allowed)
{
  const struct jnode *c;
  if (!obj)
    return 0;
  for (c = json_child(doc, obj); c; c = json_next(doc, c)) {
    int ok = 0;
    for (int i = 0; allowed[i]; i++)
      if (strcmp(allowed[i], c->key) == 0)
        ok = 1;
    if (!ok)
      return EP("bad_params", "parametro sconosciuto", "{\"field\":\"%.60s\"}", c->key);
  }
  return 0;
}

struct req {
  struct conn *c;
  const struct jdoc *doc;
  const struct jnode *params; /* oggetto (eventualmente vuoto, mai NULL per i gestori) */
};

#define KEYS(...) static const char *const keys[] = {__VA_ARGS__, 0}
#define KEYS0() static const char *const keys[] = {0}

/* ---------------------------------------------------------------- campi giocatore */

enum { F_GOLD, F_BANK, F_EXP, F_ALIGN, F_HIT, F_MANA, F_MOVE, F_PRAC, F_STR, F_STRADD, F_INT, F_WIS, F_DEX, F_CON, F_CHR, F_N };

struct fdef {
  const char *name;
  long long min, max;
};

static const struct fdef FD[F_N] = {
    {"gold", 0, 2147483647LL},  {"bankGold", 0, 2147483647LL}, {"exp", 0, 2147483647LL}, {"alignment", -1000, 1000},
    {"hit", 1, 32767},          {"mana", 0, 32767},            {"move", 0, 32767},       {"spellsToLearn", 0, 127},
    {"str", 0, 25},             {"strAdd", 0, 100},            {"int", 0, 25},           {"wis", 0, 25},
    {"dex", 0, 25},             {"con", 0, 25},                {"chr", 0, 25}};

static const char *const COND_NAMES[3] = {"drunk", "full", "thirst"};

static long long get_field(struct char_data *ch, int id)
{
  switch (id) {
  case F_GOLD: return GET_GOLD(ch);
  case F_BANK: return GET_BANK(ch);
  case F_EXP: return GET_EXP(ch);
  case F_ALIGN: return GET_ALIGNMENT(ch);
  case F_HIT: return ch->points.hit;
  case F_MANA: return ch->points.mana;
  case F_MOVE: return ch->points.move;
  case F_PRAC: return ch->specials.spells_to_learn;
  case F_STR: return ch->abilities.str;
  case F_STRADD: return ch->abilities.str_add;
  case F_INT: return ch->abilities.intel;
  case F_WIS: return ch->abilities.wis;
  case F_DEX: return ch->abilities.dex;
  case F_CON: return ch->abilities.con;
  case F_CHR: return ch->abilities.chr;
  }
  return 0;
}

static void set_field(struct char_data *ch, int id, long long v)
{
  switch (id) {
  case F_GOLD: GET_GOLD(ch) = (int)v; break;
  case F_BANK: GET_BANK(ch) = (int)v; break;
  case F_EXP: GET_EXP(ch) = (int)v; break;
  case F_ALIGN: GET_ALIGNMENT(ch) = (int)v; break;
  case F_HIT: ch->points.hit = (sh_int)v; break;
  case F_MANA: ch->points.mana = (sh_int)v; break;
  case F_MOVE: ch->points.move = (sh_int)v; break;
  case F_PRAC: ch->specials.spells_to_learn = (byte)v; break;
  case F_STR: ch->abilities.str = (sbyte)v; break;
  case F_STRADD: ch->abilities.str_add = (sbyte)v; break;
  case F_INT: ch->abilities.intel = (sbyte)v; break;
  case F_WIS: ch->abilities.wis = (sbyte)v; break;
  case F_DEX: ch->abilities.dex = (sbyte)v; break;
  case F_CON: ch->abilities.con = (sbyte)v; break;
  case F_CHR: ch->abilities.chr = (sbyte)v; break;
  }
}

static long long field_max(struct char_data *ch, int id)
{
  long long lim = FD[id].max, cur = get_field(ch, id), game;
  if (id == F_HIT)
    game = GET_MAX_HIT(ch);
  else if (id == F_MANA)
    game = GET_MAX_MANA(ch);
  else if (id == F_MOVE)
    game = GET_MAX_MOVE(ch);
  else
    return lim;
  if (game < cur)
    game = cur;
  return game < lim ? game : lim;
}

static void emit_fields(struct jw *w, struct char_data *ch, struct char_data *body)
{
  jw_raw(w, "{");
  for (int i = 0; i < F_N; i++) {
    if (i)
      jw_char(w, ',');
    jw_str(w, FD[i].name);
    jw_char(w, ':');
    jw_int(w, get_field(ch, i));
  }
  jw_raw(w, ",\"maxHit\":");
  jw_int(w, ch->points.max_hit);
  jw_raw(w, ",\"maxMana\":");
  jw_int(w, ch->points.max_mana);
  jw_raw(w, ",\"maxMove\":");
  jw_int(w, ch->points.max_move);
  jw_raw(w, ",\"race\":");
  jw_int(w, GET_RACE(ch));
  jw_raw(w, ",\"sex\":");
  jw_int(w, GET_SEX(ch));
  jw_raw(w, ",\"roomVnum\":");
  jw_int(w, body->in_room);
  jw_raw(w, ",\"conditions\":{");
  for (int i = 0; i < 3; i++) {
    if (i)
      jw_char(w, ',');
    jw_str(w, COND_NAMES[i]);
    jw_char(w, ':');
    jw_int(w, GET_COND(ch, i));
  }
  jw_raw(w, "},\"levels\":{");
  for (int i = 0, first = 1; i < MAX_CLASS; i++) {
    if (!GET_LEVEL(ch, i))
      continue;
    if (!first)
      jw_char(w, ',');
    first = 0;
    jw_str(w, CLASS_NAMES[i]);
    jw_char(w, ':');
    jw_int(w, GET_LEVEL(ch, i));
  }
  jw_raw(w, "}}");
}

static void emit_field_names(struct jw *w, int writable)
{
  jw_char(w, '[');
  for (int i = 0; i < F_N; i++) {
    if (i)
      jw_char(w, ',');
    jw_str(w, FD[i].name);
  }
  jw_raw(w, ",\"conditions\",\"levels\"");
  if (!writable)
    jw_raw(w, ",\"maxHit\",\"maxMana\",\"maxMove\",\"race\",\"sex\",\"roomVnum\"");
  jw_char(w, ']');
}

/* ---------------------------------------------------------------- comandi */

static int cmd_ping(struct req *r, struct jw *w)
{
  KEYS0();
  if (check_keys(r->doc, r->params, keys) < 0)
    return -1;
  jw_raw(w, "{\"pong\":true,\"time\":");
  jw_int(w, (long long)time(0));
  jw_char(w, '}');
  return 0;
}

static int cmd_info(struct req *r, struct jw *w)
{
  KEYS0();
  struct descriptor_data *d;
  struct char_data *p;
  int playing = 0, connecting = 0, linkdead = 0;
  if (check_keys(r->doc, r->params, keys) < 0)
    return -1;
  for (d = descriptor_list; d; d = d->next) {
    if (d->connected == CON_PLYNG)
      playing++;
    else
      connecting++;
  }
  for (p = character_list; p; p = p->next)
    if (char_ok(p) && !IS_NPC(p) && !p->desc)
      linkdead++;
  jw_raw(w, "{\"mud\":{\"kind\":\"dikumod\",\"name\":\"LeU\",\"version\":");
  jw_str(w, VERSION);
  jw_raw(w, "},\"started_at\":");
  jw_int(w, Uptime);
  jw_raw(w, ",\"now\":");
  jw_int(w, (long long)time(0));
  jw_raw(w, ",\"uptime_s\":");
  jw_int(w, (long long)time(0) - Uptime);
  jw_raw(w, ",\"pulse\":");
  jw_int(w, pulse);
  jw_raw(w, ",\"ticks\":");
  jw_int(w, L.ticks);
  jw_raw(w, ",\"lag_us\":");
  jw_int(w, GetLagIndex());
  jw_raw(w, ",\"players\":{\"playing\":");
  jw_int(w, playing);
  jw_raw(w, ",\"linkdead\":");
  jw_int(w, linkdead);
  jw_raw(w, ",\"connecting\":");
  jw_int(w, connecting);
  jw_raw(w, "},\"world\":{\"zones\":");
  jw_int(w, top_of_zone_table + 1);
  jw_raw(w, ",\"mob_protos\":");
  jw_int(w, top_of_mobt);
  jw_raw(w, ",\"obj_protos\":");
  jw_int(w, top_of_objt);
  jw_raw(w, "}}");
  return 0;
}

static int prefix_ok(const char *name, const char *prefix)
{
  return !prefix || strncasecmp(name, prefix, strlen(prefix)) == 0;
}

static void who_entry(struct jw *w, struct char_data *ch, struct char_data *body, const char *state)
{
  struct room_data *rp = real_roomp(body->in_room);
  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"state\":");
  jw_str(w, state);
  jw_raw(w, ",\"level\":");
  jw_int(w, GetMaxLevel(ch));
  jw_raw(w, ",\"levels\":{");
  for (int i = 0, first = 1; i < MAX_CLASS; i++) {
    if (!GET_LEVEL(ch, i))
      continue;
    if (!first)
      jw_char(w, ',');
    first = 0;
    jw_str(w, CLASS_NAMES[i]);
    jw_char(w, ':');
    jw_int(w, GET_LEVEL(ch, i));
  }
  jw_raw(w, "},\"race\":");
  jw_int(w, GET_RACE(ch));
  jw_raw(w, ",\"sex\":");
  jw_int(w, GET_SEX(ch));
  jw_raw(w, ",\"room\":");
  jw_int(w, body->in_room);
  jw_raw(w, ",\"zone\":");
  jw_int(w, rp ? rp->zone : -1);
  jw_raw(w, ",\"position\":");
  jw_int(w, GET_POS(body));
  jw_raw(w, ",\"fighting\":");
  jw_raw(w, body->specials.fighting ? "true" : "false");
  jw_raw(w, ",\"idle\":");
  jw_int(w, body->specials.timer);
  jw_raw(w, ",\"immortal\":");
  jw_raw(w, GetMaxLevel(ch) >= LOW_IMMORTAL ? "true" : "false");
  jw_raw(w, ",\"invisible\":");
  jw_int(w, body->invis_level);
  jw_char(w, '}');
}

static int cmd_who(struct req *r, struct jw *w)
{
  KEYS("prefix", "limit", "linkdead");
  const char *prefix = 0;
  long long limit = 100;
  int linkdead = 1, count = 0, truncated = 0, first = 1;
  struct descriptor_data *d;
  struct char_data *p;
  if (check_keys(r->doc, r->params, keys) < 0 || p_str(r->doc, r->params, "prefix", 0, &prefix) < 0 ||
      p_int(r->doc, r->params, "limit", 0, &limit) < 0 || p_bool(r->doc, r->params, "linkdead", &linkdead) < 0)
    return -1;
  if (limit < 1 || limit > 200)
    return EP("value_out_of_range", "limit fuori intervallo", "{\"field\":\"limit\",\"min\":1,\"max\":200}");
  jw_raw(w, "{\"players\":[");
  for (d = descriptor_list; d; d = d->next) {
    struct char_data *ch = d->original ? d->original : d->character;
    if (d->connected != CON_PLYNG || !char_ok(ch) || !char_ok(d->character) || !ch->player.name || !prefix_ok(ch->player.name, prefix))
      continue;
    if (count >= limit) {
      truncated = 1;
      break;
    }
    if (!first)
      jw_char(w, ',');
    first = 0;
    who_entry(w, ch, d->character, d->original ? "polymorph" : "playing");
    count++;
  }
  if (linkdead && !truncated)
    for (p = character_list; p; p = p->next) {
      if (!char_ok(p) || IS_NPC(p) || p->desc || !p->player.name || !prefix_ok(p->player.name, prefix))
        continue;
      if (count >= limit) {
        truncated = 1;
        break;
      }
      if (!first)
        jw_char(w, ',');
      first = 0;
      who_entry(w, p, p, "linkdead");
      count++;
    }
  jw_raw(w, "],\"count\":");
  jw_int(w, count);
  jw_raw(w, ",\"truncated\":");
  jw_raw(w, truncated ? "true}" : "false}");
  return 0;
}

static int cmd_player_get(struct req *r, struct jw *w)
{
  KEYS("name");
  const char *name = 0;
  struct descriptor_data *d;
  struct char_data *ch;
  if (check_keys(r->doc, r->params, keys) < 0 || p_str(r->doc, r->params, "name", 1, &name) < 0 || find_player(name, &d, &ch) < 0)
    return -1;
  set_target("%s", ch->player.name);
  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"state\":\"playing\",\"fields\":");
  emit_fields(w, ch, d->character);
  jw_char(w, '}');
  return 0;
}

/* modifica richiesta, validata ma non ancora applicata */
struct chg {
  int kind; /* 0 campo, 1 condizione, 2 livello */
  int id;
  long long v;
};

static int cmd_player_set(struct req *r, struct jw *w)
{
  KEYS("name", "set", "save", "confirm_immortal");
  const char *name = 0;
  const struct jnode *set, *m, *s;
  struct chg ch_[40];
  long long old[40];
  int n = 0, save = 1, confirm = 0, stats = 0, saved = 0, warn_immortal = 0;
  struct descriptor_data *d;
  struct char_data *ch;
  time_t before;
  char path[80];
  struct stat st;
  int nkeys = 0;

  if (check_keys(r->doc, r->params, keys) < 0 || p_str(r->doc, r->params, "name", 1, &name) < 0 ||
      p_bool(r->doc, r->params, "save", &save) < 0 || p_bool(r->doc, r->params, "confirm_immortal", &confirm) < 0)
    return -1;
  set = json_get(r->doc, r->params, "set");
  if (!set || set->type != J_OBJ)
    return EP("bad_params", "set deve essere un oggetto", "{\"field\":\"set\"}");
  if (set->n < 1 || set->n > 16)
    return EP("bad_params", "set: da 1 a 16 campi", "{\"field\":\"set\"}");
  if (find_player(name, &d, &ch) < 0 || writable_player(d) < 0)
    return -1;
  set_target("%s", ch->player.name);

  for (m = json_child(r->doc, set); m; m = json_next(r->doc, m)) {
    int id = -1;
    for (int i = 0; i < F_N; i++)
      if (strcmp(FD[i].name, m->key) == 0)
        id = i;
    if (id >= 0) {
      long long mx = field_max(ch, id);
      if (m->type != J_INT)
        return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", m->key);
      if (m->i < FD[id].min || m->i > mx)
        return EP("value_out_of_range", "valore fuori intervallo", "{\"field\":\"%s\",\"min\":%lld,\"max\":%lld}", m->key,
                  FD[id].min, mx);
      if (n >= 40)
        return E("bad_params", "troppi campi");
      ch_[n].kind = 0;
      ch_[n].id = id;
      ch_[n++].v = m->i;
      continue;
    }
    if (strcmp(m->key, "conditions") == 0 || strcmp(m->key, "levels") == 0) {
      int is_cond = m->key[0] == 'c';
      if (m->type != J_OBJ || m->n < 1)
        return EP("bad_params", "oggetto non valido", "{\"field\":\"%s\"}", m->key);
      for (s = json_child(r->doc, m); s; s = json_next(r->doc, s)) {
        int sid = -1;
        const char *const *names = is_cond ? COND_NAMES : CLASS_NAMES;
        int cnt = is_cond ? 3 : MAX_CLASS;
        for (int i = 0; i < cnt; i++)
          if (strcmp(names[i], s->key) == 0)
            sid = i;
        if (sid < 0)
          return EP("bad_params", "campo sconosciuto", "{\"field\":\"%s.%.40s\"}", m->key, s->key);
        if (s->type != J_INT)
          return EP("bad_params", "tipo non valido", "{\"field\":\"%s.%.40s\"}", m->key, s->key);
        if (is_cond) {
          if (s->i < -1 || s->i > 24)
            return EP("value_out_of_range", "valore fuori intervallo", "{\"field\":\"conditions.%s\",\"min\":-1,\"max\":24}", s->key);
        } else {
          if (s->i < 0 || s->i > IMPLEMENTOR)
            return EP("value_out_of_range", "valore fuori intervallo", "{\"field\":\"levels.%s\",\"min\":0,\"max\":%d}", s->key,
                      IMPLEMENTOR);
          if (s->i > 0 && !(ch->player.iClass & (1 << sid)))
            return EP("forbidden_by_policy", "il giocatore non ha quella classe", "{\"reason\":\"class_not_owned\",\"class\":\"%s\"}",
                      s->key);
          if (s->i >= LOW_IMMORTAL && s->i > GET_LEVEL(ch, sid)) { /* promozione: serve la conferma */
            if (!confirm)
              return EP("forbidden_by_policy", "livello da immortale: serve confirm_immortal",
                        "{\"reason\":\"immortal_level\",\"level\":%lld}", s->i);
            warn_immortal = 1;
          }
        }
        if (n >= 40)
          return E("bad_params", "troppi campi");
        ch_[n].kind = is_cond ? 1 : 2;
        ch_[n].id = sid;
        ch_[n++].v = s->i;
      }
      continue;
    }
    return EP("bad_params", "campo non modificabile", "{\"field\":\"%.60s\"}", m->key);
  }
  (void)nkeys;

  /* applicazione: da qui in poi nessun errore possibile */
  for (int i = 0; i < n; i++) {
    if (ch_[i].kind == 0) {
      old[i] = get_field(ch, ch_[i].id);
      set_field(ch, ch_[i].id, ch_[i].v);
      if (ch_[i].id >= F_STR)
        stats = 1;
    } else if (ch_[i].kind == 1) {
      old[i] = GET_COND(ch, ch_[i].id);
      GET_COND(ch, ch_[i].id) = (sbyte)ch_[i].v;
    } else {
      old[i] = GET_LEVEL(ch, ch_[i].id);
      GET_LEVEL(ch, ch_[i].id) = (byte)ch_[i].v;
    }
  }
  if (stats)
    affect_total(ch);

  if (save) {
    before = time(0);
    snprintf(path, sizeof path, "players/%s.dat", lower(ch->player.name));
    do_save(ch, (char *)"", 0);
    saved = stat(path, &st) == 0 && st.st_mtime >= before;
  }

  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"applied\":{");
  for (int i = 0; i < n; i++) {
    char key[64];
    if (ch_[i].kind == 0)
      snprintf(key, sizeof key, "%s", FD[ch_[i].id].name);
    else
      snprintf(key, sizeof key, "%s.%s", ch_[i].kind == 1 ? "conditions" : "levels",
               ch_[i].kind == 1 ? COND_NAMES[ch_[i].id] : CLASS_NAMES[ch_[i].id]);
    if (i)
      jw_char(w, ',');
    jw_str(w, key);
    jw_raw(w, ":{\"old\":");
    jw_int(w, old[i]);
    jw_raw(w, ",\"new\":");
    jw_int(w, ch_[i].v);
    jw_char(w, '}');
    add_extra("%s%s:%lld>%lld", i ? "," : "fields=", key, old[i], ch_[i].v);
  }
  jw_raw(w, "},\"saved\":");
  jw_raw(w, saved ? "true" : "false");
  jw_raw(w, ",\"warnings\":[");
  if (warn_immortal) {
    jw_raw(w, "\"immortal_level\"");
    add_extra(" confirm_immortal=1");
  }
  if (save && !saved) {
    jw_raw(w, warn_immortal ? ",\"save_failed\"" : "\"save_failed\"");
  }
  jw_raw(w, "]}");
  add_extra(" saved=%d", saved);
  return 0;
}

static int cmd_zone_list(struct req *r, struct jw *w)
{
  KEYS0();
  if (check_keys(r->doc, r->params, keys) < 0)
    return -1;
  jw_raw(w, "{\"zones\":[");
  for (int i = 0; i <= top_of_zone_table; i++) {
    struct zone_data *z = &zone_table[i];
    if (i)
      jw_char(w, ',');
    jw_raw(w, "{\"index\":");
    jw_int(w, i);
    jw_raw(w, ",\"num\":");
    jw_int(w, z->num);
    jw_raw(w, ",\"name\":");
    jw_str_latin1(w, z->name);
    jw_raw(w, ",\"top\":");
    jw_int(w, z->top);
    jw_raw(w, ",\"lifespan\":");
    jw_int(w, z->lifespan);
    jw_raw(w, ",\"age\":");
    jw_int(w, z->age);
    jw_raw(w, ",\"reset_mode\":");
    jw_int(w, z->reset_mode);
    jw_raw(w, ",\"started\":");
    jw_raw(w, z->start ? "true}" : "false}");
  }
  jw_raw(w, "]}");
  return 0;
}

static int cmd_zone_reset(struct req *r, struct jw *w)
{
  KEYS("zone", "room", "only_if_empty");
  long long zone = -1, room = -1;
  int has_zone, has_room, only_empty = 0, executed = 1;
  struct reset_q_element *e, *prev = 0;
  if (check_keys(r->doc, r->params, keys) < 0)
    return -1;
  has_zone = p_int(r->doc, r->params, "zone", 0, &zone);
  has_room = p_int(r->doc, r->params, "room", 0, &room);
  if (has_zone < 0 || has_room < 0 || p_bool(r->doc, r->params, "only_if_empty", &only_empty) < 0)
    return -1;
  if (has_zone + has_room != 1)
    return E("bad_params", "serve esattamente uno tra zone e room");
  if (has_room) {
    struct room_data *rp = room >= 0 && room < 2147483647LL ? real_roomp((long)room) : 0;
    if (!rp)
      return EP("not_found", "stanza inesistente", "{\"what\":\"room\"}");
    zone = rp->zone;
  }
  if (zone < 0 || zone > top_of_zone_table)
    return EP("not_found", "zona inesistente", "{\"what\":\"zone\"}");
  if (zone == 0)
    return EP("forbidden_by_policy", "la zona 0 non e' resettabile dal canale", "{\"reason\":\"zone_zero\"}");
  set_target("zone:%lld", zone);
  if (only_empty && !is_empty((int)zone))
    executed = 0;
  if (executed) {
    /* toglie la zona dalla coda del reset automatico (altrimenti verrebbe resettata due volte) */
    for (e = gReset_q.head; e; prev = e, e = e->next)
      if (e->zone_to_reset == zone) {
        if (prev)
          prev->next = e->next;
        else
          gReset_q.head = e->next;
        if (gReset_q.tail == e)
          gReset_q.tail = prev;
        free(e);
        break;
      }
    reset_zone((int)zone);
  }
  jw_raw(w, "{\"zone\":");
  jw_int(w, zone);
  jw_raw(w, ",\"name\":");
  jw_str_latin1(w, zone_table[zone].name);
  jw_raw(w, ",\"executed\":");
  jw_raw(w, executed ? "true}" : "false}");
  return 0;
}

static int denied(long vnum)
{
  for (int i = 0; i < L.ndeny; i++)
    if (vnum >= L.deny[i].lo && vnum <= L.deny[i].hi)
      return 1;
  return 0;
}

/* destinazione di load.* : stanza o giocatore. *room = vnum stanza, *target = giocatore o NULL */
static int load_target(struct req *r, long *room, struct char_data **target)
{
  long long rv = -1;
  const char *pname = 0;
  int hr = p_int(r->doc, r->params, "room", 0, &rv), hp = p_str(r->doc, r->params, "player", 0, &pname);
  *target = 0;
  if (hr < 0 || hp < 0)
    return -1;
  if (hr + hp != 1)
    return E("bad_params", "serve esattamente uno tra room e player");
  if (hr) {
    if (rv < 0 || rv > 2147483646LL || !real_roomp((long)rv))
      return EP("not_found", "stanza inesistente", "{\"what\":\"room\"}");
    *room = (long)rv;
    set_target("room:%ld", *room);
  } else {
    struct descriptor_data *d;
    struct char_data *ch;
    if (find_player(pname, &d, &ch) < 0)
      return -1;
    *target = d->character;
    *room = d->character->in_room;
    set_target("%s", ch->player.name);
  }
  return 0;
}

static int cmd_load_mob(struct req *r, struct jw *w)
{
  KEYS("vnum", "room", "player", "count", "notify");
  long long vnum = 0, count = 1;
  int notify = 0;
  long room = 0;
  struct char_data *target;
  if (check_keys(r->doc, r->params, keys) < 0 || p_int(r->doc, r->params, "vnum", 1, &vnum) < 0 ||
      p_int(r->doc, r->params, "count", 0, &count) < 0 || p_bool(r->doc, r->params, "notify", &notify) < 0 ||
      load_target(r, &room, &target) < 0)
    return -1;
  if (count < 1 || count > 10)
    return EP("value_out_of_range", "count fuori intervallo", "{\"field\":\"count\",\"min\":1,\"max\":10}");
  if (vnum < 0 || vnum > 2147483646LL || real_mobile((int)vnum) < 0)
    return EP("not_found", "mob inesistente", "{\"what\":\"mob\"}");
  add_extra("vnum=%lld count=%lld", vnum, count);
  jw_raw(w, "{\"loaded\":[");
  for (int i = 0; i < count; i++) {
    struct char_data *mob = read_mobile((int)vnum, VIRTUAL);
    if (!mob) {
      if (i == 0)
        return E("internal", "creazione del mob fallita");
      break;
    }
    char_to_room(mob, room);
    if (i)
      jw_char(w, ',');
    jw_raw(w, "{\"vnum\":");
    jw_int(w, vnum);
    jw_raw(w, ",\"name\":");
    jw_str_latin1(w, mob->player.short_descr);
    jw_raw(w, ",\"room\":");
    jw_int(w, room);
    jw_char(w, '}');
  }
  jw_raw(w, "]}");
  if (notify)
    send_to_room((char *)"Qualcosa di nuovo appare.\n\r", (int)room);
  return 0;
}

static int cmd_load_obj(struct req *r, struct jw *w)
{
  KEYS("vnum", "room", "player", "count", "notify");
  long long vnum = 0, count = 1;
  int notify = 0;
  long room = 0;
  struct char_data *target;
  if (check_keys(r->doc, r->params, keys) < 0 || p_int(r->doc, r->params, "vnum", 1, &vnum) < 0 ||
      p_int(r->doc, r->params, "count", 0, &count) < 0 || p_bool(r->doc, r->params, "notify", &notify) < 0 ||
      load_target(r, &room, &target) < 0)
    return -1;
  if (count < 1 || count > 10)
    return EP("value_out_of_range", "count fuori intervallo", "{\"field\":\"count\",\"min\":1,\"max\":10}");
  if (vnum < 0 || vnum > 2147483646LL || real_object((int)vnum) < 0)
    return EP("not_found", "oggetto inesistente", "{\"what\":\"object\"}");
  if (denied((long)vnum))
    return EP("forbidden_by_policy", "oggetto non creabile dal canale", "{\"reason\":\"deny_list\",\"vnum\":%lld}", vnum);
  add_extra("vnum=%lld count=%lld", vnum, count);
  jw_raw(w, "{\"loaded\":[");
  for (int i = 0; i < count; i++) {
    struct obj_data *obj = read_object((int)vnum, VIRTUAL);
    if (!obj) {
      if (i == 0)
        return E("internal", "creazione dell'oggetto fallita");
      break;
    }
    if (target)
      obj_to_char(obj, target);
    else
      obj_to_room(obj, room);
    if (i)
      jw_char(w, ',');
    jw_raw(w, "{\"vnum\":");
    jw_int(w, vnum);
    jw_raw(w, ",\"name\":");
    jw_str_latin1(w, obj->short_description);
    jw_raw(w, ",\"where\":");
    {
      char wh[40];
      if (target)
        snprintf(wh, sizeof wh, "player");
      else
        snprintf(wh, sizeof wh, "room:%ld", room);
      jw_str(w, wh);
    }
    jw_char(w, '}');
  }
  jw_raw(w, "],\"warnings\":[");
  if (target && vnum > 32767) /* il rent salva item_number come sh_int: oltre 32767 il vnum si corrompe al salvataggio */
    jw_raw(w, "\"vnum_not_saveable\"");
  jw_raw(w, "]}");
  if (notify)
    send_to_room((char *)"Qualcosa di nuovo appare.\n\r", (int)room);
  return 0;
}

static int cmd_echo(struct req *r, struct jw *w)
{
  KEYS("text", "to");
  const char *text = 0;
  const struct jnode *to, *t;
  char lat[LC_MAX_TEXT + 1], msg[2 * LC_MAX_TEXT + 8];
  int n, o = 0, recipients = 0;
  if (check_keys(r->doc, r->params, keys) < 0 || p_str(r->doc, r->params, "text", 1, &text) < 0)
    return -1;
  to = json_get(r->doc, r->params, "to");
  if (!to || to->type != J_OBJ || to->n != 1)
    return EP("bad_params", "to deve avere una sola chiave", "{\"field\":\"to\"}");
  n = utf8_to_latin1(text, lat, (int)sizeof lat);
  if (n == -2)
    return EP("bad_params", "testo troppo lungo", "{\"field\":\"text\",\"max\":%d}", LC_MAX_TEXT);
  if (n < 0)
    return E("unencodable_text", "testo non rappresentabile in latin-1");
  if (n == 0)
    return EP("bad_params", "testo vuoto", "{\"field\":\"text\"}");
  for (int i = 0; i < n; i++) {
    unsigned char c = (unsigned char)lat[i];
    if (c < 0x20 || c == 0x7f)
      return EP("bad_params", "caratteri di controllo non ammessi", "{\"field\":\"text\"}");
    if (c == '$')
      msg[o++] = '\\'; /* neutralizza i codici colore $c del gioco (ParseAnsiColors) */
    msg[o++] = (char)c;
  }
  msg[o++] = '\n';
  msg[o++] = '\r';
  msg[o] = 0;
  t = json_child(r->doc, to);
  if (strcmp(t->key, "all") == 0) {
    struct descriptor_data *d;
    if (t->type != J_BOOL || t->i != 1)
      return EP("bad_params", "all deve essere true", "{\"field\":\"to.all\"}");
    for (d = descriptor_list; d; d = d->next)
      if (d->connected == CON_PLYNG && char_ok(d->character))
        recipients++;
    set_target("all");
    send_to_all(msg);
  } else if (strcmp(t->key, "player") == 0) {
    struct descriptor_data *d;
    struct char_data *ch;
    if (t->type != J_STR)
      return EP("bad_params", "tipo non valido", "{\"field\":\"to.player\"}");
    if (find_player(t->s, &d, &ch) < 0)
      return -1;
    set_target("%s", ch->player.name);
    send_to_char(msg, d->character);
    recipients = 1;
  } else if (strcmp(t->key, "room") == 0) {
    struct room_data *rp;
    struct char_data *p;
    if (t->type != J_INT || t->i < 0 || t->i > 2147483646LL || !(rp = real_roomp((long)t->i)))
      return EP("not_found", "stanza inesistente", "{\"what\":\"room\"}");
    for (p = rp->people; p; p = p->next_in_room)
      if (p->desc)
        recipients++;
    set_target("room:%lld", t->i);
    send_to_room(msg, (int)t->i);
  } else {
    return EP("bad_params", "destinatario sconosciuto", "{\"field\":\"to\"}");
  }
  {
    char tmp[84];
    snprintf(tmp, sizeof tmp, "%.80s", lat);
    for (char *q = tmp; *q; q++)
      if (*q == ' ')
        *q = '_';
    add_extra("text=%s", tmp);
  }
  jw_raw(w, "{\"recipients\":");
  jw_int(w, recipients);
  jw_char(w, '}');
  return 0;
}

/* ---------------------------------------------------------------- inventario e oggetti istanza (feature "inventory") */

#define LC_MAX_REF_DEPTH 8     /* profondita' massima di annidamento nei contenitori */
#define LC_MAX_INV_ITEMS 200
#define LC_LEN_NAME      127   /* obj_file_elem.name[128]: put_obj_in_store usa strcpy senza limite */
#define LC_LEN_SHORT     127   /* obj_file_elem.sd[128] */
#define LC_LEN_DESC      255   /* obj_file_elem.desc[256] */
#define LC_MAX_APPLY     64    /* APPLY_T_MANA, l'ultimo valore di affect_modify */

/* Un riferimento a un oggetto e' un PERCORSO, mai un puntatore: "eq:<slot>" o "inv:<indice>", seguito da "/<indice>" per ogni
 * contenitore attraversato (indici nella lista contains). Va risolto a ogni richiesta e accompagnato da un controllo di impronta. */
struct oref {
  int eq, first, npath;
  int path[LC_MAX_REF_DEPTH];
};

static int parse_ref(const char *s, struct oref *r)
{
  const char *p = s;
  char *end;
  long v;
  memset(r, 0, sizeof *r);
  if (strncmp(p, "eq:", 3) == 0) {
    r->eq = 1;
    p += 3;
  } else if (strncmp(p, "inv:", 4) == 0) {
    p += 4;
  } else {
    return -1;
  }
  if (!isdigit((unsigned char)*p))
    return -1;
  v = strtol(p, &end, 10);
  if (v < 0 || v > 100000 || end - p > 6)
    return -1;
  r->first = (int)v;
  p = end;
  while (*p == '/') {
    p++;
    if (!isdigit((unsigned char)*p) || r->npath >= LC_MAX_REF_DEPTH)
      return -1;
    v = strtol(p, &end, 10);
    if (v < 0 || v > 100000 || end - p > 6)
      return -1;
    r->path[r->npath++] = (int)v;
    p = end;
  }
  return *p ? -1 : 0;
}

static struct obj_data *nth(struct obj_data *list, int n)
{
  int guard = 0;
  while (list && n > 0 && guard++ < 100000) {
    list = list->next_content;
    n--;
  }
  return n == 0 ? list : 0;
}

static struct obj_data *resolve_ref(struct char_data *ch, const struct oref *r)
{
  struct obj_data *o;
  if (r->eq)
    o = r->first >= 0 && r->first < MAX_WEAR ? ch->equipment[r->first] : 0;
  else
    o = nth(ch->carrying, r->first);
  for (int i = 0; o && i < r->npath; i++)
    o = nth(o->contains, r->path[i]);
  return o;
}

static int obj_vnum(const struct obj_data *o)
{
  return o->item_number >= 0 && o->item_number < top_of_objt ? obj_index[o->item_number].iVNum : -1;
}

static unsigned fp_bytes(unsigned h, const void *p, size_t n)
{
  const unsigned char *b = (const unsigned char *)p;
  while (n--)
    h = (h ^ *b++) * 16777619u;
  return h;
}

static unsigned fp_str(unsigned h, const char *s)
{
  return fp_bytes(h, s ? s : "", s ? strlen(s) + 1 : 1);
}

/* impronta (FNV-1a a 32 bit) di vnum, testi, flag, valori e affect: NON include peso e timer, che cambiano da soli */
static unsigned obj_fp(const struct obj_data *o)
{
  unsigned h = 2166136261u;
  int v = obj_vnum(o), type = o->obj_flags.type_flag;
  unsigned long ef = o->obj_flags.extra_flags;
  h = fp_bytes(h, &v, sizeof v);
  h = fp_bytes(h, &type, sizeof type);
  h = fp_str(h, o->name);
  h = fp_str(h, o->short_description);
  h = fp_str(h, o->description);
  h = fp_bytes(h, &ef, sizeof ef);
  h = fp_bytes(h, o->obj_flags.value, sizeof o->obj_flags.value);
  for (int i = 0; i < MAX_OBJ_AFFECT; i++) {
    int loc = o->affected[i].location, mod = o->affected[i].modifier;
    h = fp_bytes(h, &loc, sizeof loc);
    h = fp_bytes(h, &mod, sizeof mod);
  }
  return h;
}

static struct obj_data *top_of(struct obj_data *o)
{
  int guard = 0;
  while (o->in_obj && guard++ < 64)
    o = o->in_obj;
  return o;
}

/* campi modificabili e di sola lettura di un oggetto */
static void emit_obj_fields(struct jw *w, const struct obj_data *o)
{
  jw_raw(w, ",\"description\":");
  jw_str_latin1(w, o->description);
  jw_raw(w, ",\"values\":[");
  for (int i = 0; i < 4; i++) {
    if (i)
      jw_char(w, ',');
    jw_int(w, o->obj_flags.value[i]);
  }
  jw_raw(w, "],\"weight\":");
  jw_int(w, o->obj_flags.weight);
  jw_raw(w, ",\"extra_flags\":");
  jw_int(w, (long long)o->obj_flags.extra_flags);
  jw_raw(w, ",\"timer\":");
  jw_int(w, o->obj_flags.timer);
  jw_raw(w, ",\"affects\":[");
  for (int i = 0; i < MAX_OBJ_AFFECT; i++) {
    if (i)
      jw_char(w, ',');
    jw_raw(w, "{\"location\":");
    jw_int(w, o->affected[i].location);
    jw_raw(w, ",\"modifier\":");
    jw_int(w, o->affected[i].modifier);
    jw_char(w, '}');
  }
  jw_char(w, ']');
}

static void emit_obj(struct jw *w, const struct obj_data *o, const char *ref, int slot, int depth, int brief, int full)
{
  const struct obj_data *c;
  int n = 0, v = obj_vnum(o);
  char fp[12];
  snprintf(fp, sizeof fp, "%08x", obj_fp(o));
  for (c = o->contains; c && n < 100000; c = c->next_content)
    n++;
  jw_raw(w, "{\"ref\":");
  jw_str(w, ref);
  jw_raw(w, ",\"fp\":\"");
  jw_raw(w, fp);
  jw_raw(w, "\",\"vnum\":");
  if (v < 0)
    jw_raw(w, "null");
  else
    jw_int(w, v);
  jw_raw(w, ",\"slot\":");
  if (slot < 0)
    jw_raw(w, "null");
  else
    jw_int(w, slot);
  jw_raw(w, ",\"depth\":");
  jw_int(w, depth);
  jw_raw(w, ",\"name\":");
  jw_str_latin1(w, o->name);
  jw_raw(w, ",\"short_description\":");
  jw_str_latin1(w, o->short_description);
  jw_raw(w, ",\"type\":");
  jw_int(w, o->obj_flags.type_flag);
  jw_raw(w, ",\"contents\":");
  jw_int(w, n);
  if (!brief)
    emit_obj_fields(w, o);
  if (full) {
    jw_raw(w, ",\"wear_flags\":");
    jw_int(w, (long long)o->obj_flags.wear_flags);
    jw_raw(w, ",\"cost\":");
    jw_int(w, o->obj_flags.cost);
    jw_raw(w, ",\"cost_per_day\":");
    jw_int(w, o->obj_flags.cost_per_day);
    jw_raw(w, ",\"bitvector\":");
    jw_int(w, o->obj_flags.bitvector);
  }
  jw_char(w, '}');
}

struct walk {
  struct jw *w;
  int brief, count, limit, first, truncated;
};

static void walk_list(struct walk *k, struct obj_data *list, const char *prefix, int depth, int slot_known)
{
  int idx = 0, guard = 0;
  struct obj_data *o;
  (void)slot_known;
  for (o = list; o && guard++ < 100000; o = o->next_content, idx++) {
    char ref[96];
    snprintf(ref, sizeof ref, "%s%s%d", prefix, depth == 0 ? "" : "/", idx);
    if (k->count >= k->limit || k->w->len > LC_MAX_RESP - 4000) {
      k->truncated = 1;
      return;
    }
    if (!k->first)
      jw_char(k->w, ',');
    k->first = 0;
    emit_obj(k->w, o, ref, -1, depth, k->brief, 0);
    k->count++;
    if (o->contains) {
      if (depth + 1 >= LC_MAX_REF_DEPTH)
        k->truncated = 1;
      else
        walk_list(k, o->contains, ref, depth + 1, 0);
    }
  }
}

static int cmd_player_inventory(struct req *r, struct jw *w)
{
  KEYS("name", "brief", "limit");
  const char *name = 0;
  long long limit = 100;
  int brief = 0;
  struct descriptor_data *d;
  struct char_data *ch;
  struct walk k;
  if (check_keys(r->doc, r->params, keys) < 0 || p_str(r->doc, r->params, "name", 1, &name) < 0 ||
      p_bool(r->doc, r->params, "brief", &brief) < 0 || p_int(r->doc, r->params, "limit", 0, &limit) < 0 ||
      find_player(name, &d, &ch) < 0)
    return -1;
  if (limit < 1 || limit > LC_MAX_INV_ITEMS)
    return EP("value_out_of_range", "limit fuori intervallo", "{\"field\":\"limit\",\"min\":1,\"max\":%d}", LC_MAX_INV_ITEMS);
  set_target("%s", ch->player.name);
  k.w = w;
  k.brief = brief;
  k.count = 0;
  k.limit = (int)limit;
  k.first = 1;
  k.truncated = 0;
  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"carry_weight\":");
  jw_int(w, IS_CARRYING_W(ch));
  jw_raw(w, ",\"carry_items\":");
  jw_int(w, IS_CARRYING_N(ch));
  jw_raw(w, ",\"items\":[");
  for (int slot = 0; slot < MAX_WEAR && !k.truncated; slot++) {
    char ref[32];
    struct obj_data *o = ch->equipment[slot];
    if (!o)
      continue;
    if (k.count >= k.limit || w->len > LC_MAX_RESP - 4000) {
      k.truncated = 1;
      break;
    }
    snprintf(ref, sizeof ref, "eq:%d", slot);
    if (!k.first)
      jw_char(w, ',');
    k.first = 0;
    emit_obj(w, o, ref, slot, 0, brief, 0);
    k.count++;
    if (o->contains)
      walk_list(&k, o->contains, ref, 1, 1);
  }
  if (!k.truncated) {
    /* inventario: gli indici dei livelli annidati si accodano al riferimento "inv:<i>" */
    struct obj_data *o;
    int idx = 0, guard = 0;
    for (o = ch->carrying; o && guard++ < 100000; o = o->next_content, idx++) {
      char ref[32];
      if (k.count >= k.limit || w->len > LC_MAX_RESP - 4000) {
        k.truncated = 1;
        break;
      }
      snprintf(ref, sizeof ref, "inv:%d", idx);
      if (!k.first)
        jw_char(w, ',');
      k.first = 0;
      emit_obj(w, o, ref, -1, 0, brief, 0);
      k.count++;
      if (o->contains) {
        if (LC_MAX_REF_DEPTH <= 1)
          k.truncated = 1;
        else
          walk_list(&k, o->contains, ref, 1, 0);
      }
      if (k.truncated)
        break;
    }
  }
  jw_raw(w, "],\"count\":");
  jw_int(w, k.count);
  jw_raw(w, ",\"truncated\":");
  jw_raw(w, k.truncated ? "true}" : "false}");
  return 0;
}

/* parametri comuni a obj.*: name, ref (+ expect); risolve l'oggetto. need_expect: obbligatorio nelle scritture. */
static int obj_target(struct req *r, int need_expect, struct descriptor_data **dp, struct char_data **chp, struct obj_data **op)
{
  const char *name = 0, *refs = 0;
  const struct jnode *ex;
  struct oref ref;
  struct obj_data *o;
  if (p_str(r->doc, r->params, "name", 1, &name) < 0 || p_str(r->doc, r->params, "ref", 1, &refs) < 0)
    return -1;
  if (parse_ref(refs, &ref) < 0)
    return EP("bad_params", "ref non valido", "{\"field\":\"ref\"}");
  if (find_player(name, dp, chp) < 0)
    return -1;
  set_target("%s", (*chp)->player.name);
  add_extra("ref=%s ", refs);
  ex = json_get(r->doc, r->params, "expect");
  if (need_expect && !ex)
    return EP("bad_params", "expect obbligatorio nelle scritture", "{\"field\":\"expect\"}");
  o = resolve_ref(*chp, &ref);
  if (!o)
    return need_expect || ex ? E("stale_ref", "l'oggetto non e' piu' li'") : EP("not_found", "oggetto inesistente", "{\"what\":\"object\"}");
  if (ex) {
    const char *fp = 0;
    long long vn = 0;
    char mine[12];
    static const char *const ekeys[] = {"vnum", "fp", 0};
    if (ex->type != J_OBJ || check_keys(r->doc, ex, ekeys) < 0)
      return EP("bad_params", "expect non valido", "{\"field\":\"expect\"}");
    {
      const struct jnode *vv = json_get(r->doc, ex, "vnum"), *ff = json_get(r->doc, ex, "fp");
      if (!vv || !ff || ff->type != J_STR || (vv->type != J_INT && vv->type != J_NULL))
        return EP("bad_params", "expect richiede vnum e fp", "{\"field\":\"expect\"}");
      fp = ff->s;
      vn = vv->type == J_INT ? vv->i : -1;
    }
    snprintf(mine, sizeof mine, "%08x", obj_fp(o));
    if (vn != obj_vnum(o) || strcmp(fp, mine) != 0)
      return E("stale_ref", "l'oggetto e' cambiato dopo l'ultima lettura");
  }
  *op = o;
  return 0;
}

static int ref_depth(const char *ref)
{
  int n = 0;
  for (; *ref; ref++)
    n += *ref == '/';
  return n;
}

static int cmd_obj_get(struct req *r, struct jw *w)
{
  KEYS("name", "ref", "expect");
  struct descriptor_data *d;
  struct char_data *ch;
  struct obj_data *o;
  if (check_keys(r->doc, r->params, keys) < 0 || obj_target(r, 0, &d, &ch, &o) < 0)
    return -1;
  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"item\":");
  {
    struct jnode *ref = (struct jnode *)json_get(r->doc, r->params, "ref");
    emit_obj(w, o, ref->s, o->equipped_by ? o->eq_pos : -1, ref_depth(ref->s), 0, 1);
  }
  jw_char(w, '}');
  return 0;
}

/* testo di un oggetto: latin-1, lunghezza massima del record di rent, niente controlli/$/~ */
static int obj_text(const char *utf8, int maxlen, const char *field, char *out, int cap)
{
  int n = utf8_to_latin1(utf8, out, cap);
  if (n == -1)
    return EP("unencodable_text", "testo non rappresentabile in latin-1", "{\"field\":\"%s\"}", field);
  if (n < 0 || n > maxlen)
    return EP("bad_params", "testo troppo lungo", "{\"field\":\"%s\",\"max\":%d}", field, maxlen);
  if (n == 0)
    return EP("bad_params", "testo vuoto", "{\"field\":\"%s\"}", field);
  for (int i = 0; i < n; i++) {
    unsigned char c = (unsigned char)out[i];
    if (c < 0x20 || c == 0x7f || c == '$' || c == '~')
      return EP("bad_params", "carattere non ammesso ($, ~ o di controllo)", "{\"field\":\"%s\"}", field);
  }
  return 0;
}

/* true se p e' una stringa posseduta dal prototipo (indice o copia in memoria): non va mai liberata dall'istanza */
static int proto_owns(const struct obj_data *o, const char *p)
{
  const struct obj_data *pd;
  if (!p || o->item_number < 0 || o->item_number >= top_of_objt)
    return 0;
  if (p == obj_index[o->item_number].name || p == obj_index[o->item_number].short_desc || p == obj_index[o->item_number].long_desc)
    return 1;
  pd = (const struct obj_data *)obj_index[o->item_number].data;
  return pd && (p == pd->name || p == pd->short_description || p == pd->description || p == pd->action_description);
}

/* sostituisce *field con una copia allocata di nuovo; la vecchia si libera solo se non e' del prototipo */
static void replace_string(struct obj_data *o, char **field, char *fresh)
{
  char *old = *field;
  *field = fresh;
  if (old && !proto_owns(o, old))
    free(old);
}

enum { OC_NAME, OC_SHORT, OC_DESC, OC_VALUE, OC_WEIGHT, OC_EXTRA, OC_TIMER, OC_AFFECT };

struct ochg {
  int kind, idx;
  long long v, v2;
  char *text; /* copia allocata (latin-1) per i testi */
};

static void free_chg(struct ochg *c, int n)
{
  for (int i = 0; i < n; i++)
    free(c[i].text);
}

static void reattach(struct char_data *ch, struct obj_data *top, int pos)
{
  /* ripete la parte finale di equip_char SENZA i controlli (ego, allineamento, ...) che potrebbero buttare l'oggetto a terra */
  ch->equipment[pos] = top;
  top->equipped_by = ch;
  top->eq_pos = pos;
  if (GET_ITEM_TYPE(top) == ITEM_ARMOR)
    GET_AC(ch) -= apply_ac(ch, pos);
  for (int j = 0; j < MAX_OBJ_AFFECT; j++)
    affect_modify(ch, top->affected[j].location, top->affected[j].modifier, top->obj_flags.bitvector, TRUE);
  affect_total(ch);
  if (pos != WEAR_BACK) /* NO_PESO_ON_BACK */
    IS_CARRYING_W(ch) += GET_OBJ_WEIGHT(top);
}

static int cmd_obj_set(struct req *r, struct jw *w)
{
  KEYS("name", "ref", "expect", "set", "save");
  static const char *const okeys[] = {"name", "short_description", "description", "values", "weight", "extra_flags", "timer", "affects", 0};
  struct descriptor_data *d;
  struct char_data *ch;
  struct obj_data *o, *top;
  const struct jnode *set, *m, *e;
  struct ochg chg[16];
  char buf[300];
  int n = 0, save = 1, saved = 0, pos = -1, equipped;
  time_t before;
  char path[80];
  struct stat st;
  if (check_keys(r->doc, r->params, keys) < 0 || p_bool(r->doc, r->params, "save", &save) < 0)
    return -1;
  set = json_get(r->doc, r->params, "set");
  if (!set || set->type != J_OBJ || set->n < 1)
    return EP("bad_params", "set deve essere un oggetto non vuoto", "{\"field\":\"set\"}");
  if (check_keys(r->doc, set, okeys) < 0 || obj_target(r, 1, &d, &ch, &o) < 0 || writable_player(d) < 0)
    return -1;
  /* il controllo di coerenza evita un assert del gioco: un oggetto annidato non deve risultare anche portato/equipaggiato */
  if (o->in_obj && (o->carried_by || o->equipped_by))
    return E("internal", "oggetto in uno stato incoerente");

  memset(chg, 0, sizeof chg);
  for (m = json_child(r->doc, set); m; m = json_next(r->doc, m)) {
    const char *k = m->key;
    if (!strcmp(k, "name") || !strcmp(k, "short_description") || !strcmp(k, "description")) {
      int kind = !strcmp(k, "name") ? OC_NAME : !strcmp(k, "short_description") ? OC_SHORT : OC_DESC;
      int maxlen = kind == OC_NAME ? LC_LEN_NAME : kind == OC_SHORT ? LC_LEN_SHORT : LC_LEN_DESC;
      if (m->type != J_STR) {
        free_chg(chg, n);
        return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", k);
      }
      if (obj_text(m->s, maxlen, k, buf, sizeof buf) < 0) {
        free_chg(chg, n);
        return -1;
      }
      chg[n].kind = kind;
      chg[n].text = strdup(buf);
      if (!chg[n].text) {
        free_chg(chg, n);
        return E("internal", "memoria esaurita");
      }
      n++;
    } else if (!strcmp(k, "values")) {
      int i = 0;
      if (m->type != J_ARR || m->n < 1 || m->n > 4) {
        free_chg(chg, n);
        return EP("bad_params", "values: array di 1-4 elementi", "{\"field\":\"values\"}");
      }
      for (e = json_child(r->doc, m); e; e = json_next(r->doc, e), i++) {
        if (e->type == J_NULL)
          continue;
        if (e->type != J_INT) {
          free_chg(chg, n);
          return EP("bad_params", "tipo non valido", "{\"field\":\"values.%d\"}", i);
        }
        if (e->i < -2147483647LL || e->i > 2147483647LL) {
          free_chg(chg, n);
          return EP("value_out_of_range", "valore fuori intervallo", "{\"field\":\"values.%d\",\"min\":-2147483647,\"max\":2147483647}", i);
        }
        chg[n].kind = OC_VALUE;
        chg[n].idx = i;
        chg[n++].v = e->i;
      }
    } else if (!strcmp(k, "weight") || !strcmp(k, "extra_flags") || !strcmp(k, "timer")) {
      long long lo = 0, hi = 2147483647LL;
      int kind = !strcmp(k, "weight") ? OC_WEIGHT : !strcmp(k, "extra_flags") ? OC_EXTRA : OC_TIMER;
      if (kind == OC_WEIGHT)
        hi = 32767;
      if (m->type != J_INT) {
        free_chg(chg, n);
        return EP("bad_params", "tipo non valido", "{\"field\":\"%s\"}", k);
      }
      if (kind == OC_TIMER && m->i == OBJ_NOTIMER) {
        /* nessun timer */
      } else if (m->i < lo || m->i > (kind == OC_TIMER ? 1000000 : hi)) {
        free_chg(chg, n);
        return EP("value_out_of_range", "valore fuori intervallo", "{\"field\":\"%s\",\"min\":%lld,\"max\":%lld}", k, lo,
                  kind == OC_TIMER ? 1000000LL : hi);
      }
      chg[n].kind = kind;
      chg[n++].v = m->i;
    } else if (!strcmp(k, "affects")) {
      int i = 0;
      static const char *const akeys[] = {"location", "modifier", 0};
      if (m->type != J_ARR || m->n < 1 || m->n > MAX_OBJ_AFFECT) {
        free_chg(chg, n);
        return EP("bad_params", "affects: array di 1-5 elementi", "{\"field\":\"affects\"}");
      }
      for (e = json_child(r->doc, m); e; e = json_next(r->doc, e), i++) {
        const struct jnode *lo, *mo;
        if (e->type == J_NULL)
          continue;
        lo = json_get(r->doc, e, "location");
        mo = json_get(r->doc, e, "modifier");
        if (e->type != J_OBJ || !lo || !mo || lo->type != J_INT || mo->type != J_INT || check_keys(r->doc, e, akeys) < 0) {
          free_chg(chg, n);
          return EP("bad_params", "affect: {location, modifier} interi", "{\"field\":\"affects.%d\"}", i);
        }
        if (lo->i < 0 || lo->i > LC_MAX_APPLY || mo->i < -32768 || mo->i > 32767) {
          free_chg(chg, n);
          return EP("value_out_of_range", "affect fuori intervallo",
                    "{\"field\":\"affects.%d\",\"location\":{\"min\":0,\"max\":%d},\"modifier\":{\"min\":-32768,\"max\":32767}}", i, LC_MAX_APPLY);
        }
        chg[n].kind = OC_AFFECT;
        chg[n].idx = i;
        chg[n].v = lo->i;
        chg[n++].v2 = mo->i;
      }
    }
    if (n >= 15) {
      free_chg(chg, n);
      return E("bad_params", "troppe modifiche");
    }
  }
  if (n == 0) {
    return E("bad_params", "nessuna modifica");
  }

  /* ---- applicazione: nessun errore possibile da qui ---- */
  top = top_of(o);
  equipped = top->equipped_by == ch && top->eq_pos >= 0;
  if (equipped) {
    pos = top->eq_pos;
    unequip_char(ch, pos); /* toglie bonus e peso; il ripristino non rifa' i controlli di equip_char */
  }
  for (int i = 0; i < n; i++) {
    struct ochg *c = &chg[i];
    switch (c->kind) {
    case OC_NAME: replace_string(o, &o->name, c->text); c->text = 0; add_extra("name "); break;
    case OC_SHORT: replace_string(o, &o->short_description, c->text); c->text = 0; add_extra("short_description "); break;
    case OC_DESC: replace_string(o, &o->description, c->text); c->text = 0; add_extra("description "); break;
    case OC_VALUE:
      add_extra("values.%d:%d>%lld ", c->idx, o->obj_flags.value[c->idx], c->v);
      o->obj_flags.value[c->idx] = (int)c->v;
      break;
    case OC_EXTRA:
      add_extra("extra_flags:%lu>%lld ", o->obj_flags.extra_flags, c->v);
      o->obj_flags.extra_flags = (unsigned long)c->v;
      break;
    case OC_TIMER:
      add_extra("timer:%d>%lld ", o->obj_flags.timer, c->v);
      o->obj_flags.timer = (int)c->v;
      break;
    case OC_AFFECT:
      add_extra("affects.%d ", c->idx);
      o->affected[c->idx].location = (short)c->v;
      o->affected[c->idx].modifier = (int32_t)c->v2;
      break;
    case OC_WEIGHT: {
      int delta = (int)c->v - o->obj_flags.weight;
      struct obj_data *a;
      int guard = 0;
      add_extra("weight:%d>%lld ", o->obj_flags.weight, c->v);
      o->obj_flags.weight = (int)c->v;
      /* il peso di un contenitore comprende il contenuto: lo stesso delta sale lungo i contenitori e al personaggio che porta */
      for (a = o->in_obj; a && guard++ < 64; a = a->in_obj) {
        a->obj_flags.weight += delta;
        if (a->obj_flags.weight < 0)
          a->obj_flags.weight = 0;
      }
      if (!equipped && top->carried_by == ch) {
        IS_CARRYING_W(ch) += delta;
        if (IS_CARRYING_W(ch) < 0)
          IS_CARRYING_W(ch) = 0;
      }
      break;
    }
    }
  }
  free_chg(chg, n);
  if (equipped)
    reattach(ch, top, pos);

  if (save) {
    before = time(0);
    snprintf(path, sizeof path, "players/%s.dat", lower(ch->player.name));
    do_save(ch, (char *)"", 0);
    saved = stat(path, &st) == 0 && st.st_mtime >= before;
  }
  add_extra("saved=%d", saved);
  {
    char fp[12];
    snprintf(fp, sizeof fp, "%08x", obj_fp(o));
    jw_raw(w, "{\"name\":");
    jw_str_latin1(w, ch->player.name);
    jw_raw(w, ",\"fp\":\"");
    jw_raw(w, fp);
    jw_raw(w, "\",\"saved\":");
    jw_raw(w, saved ? "true" : "false");
    jw_raw(w, ",\"warnings\":[");
    if (save && !saved)
      jw_raw(w, "\"save_failed\"");
    jw_raw(w, "],\"item\":");
    {
      struct jnode *ref = (struct jnode *)json_get(r->doc, r->params, "ref");
      emit_obj(w, o, ref->s, equipped ? pos : -1, ref_depth(ref->s), 0, 1);
    }
    jw_char(w, '}');
  }
  return 0;
}

static int cmd_obj_remove(struct req *r, struct jw *w)
{
  KEYS("name", "ref", "expect", "save");
  struct descriptor_data *d;
  struct char_data *ch;
  struct obj_data *o;
  int save = 1, saved = 0, destroyed = 0;
  time_t before;
  char path[80];
  struct stat st;
  const struct obj_data *c;
  if (check_keys(r->doc, r->params, keys) < 0 || p_bool(r->doc, r->params, "save", &save) < 0 || obj_target(r, 1, &d, &ch, &o) < 0 ||
      writable_player(d) < 0)
    return -1;
  if (o->in_obj && (o->carried_by || o->equipped_by))
    return E("internal", "oggetto in uno stato incoerente");
  destroyed = 1;
  for (c = o->contains; c && destroyed < 100000; c = c->next_content)
    destroyed++; /* conta solo il primo livello: informativo */
  add_extra("vnum=%d items=%d ", obj_vnum(o), destroyed);
  if (o->in_obj)
    obj_from_obj(o); /* aggiorna i pesi dei contenitori e di chi li porta */
  extract_obj(o);    /* se e' un contenitore distrugge anche il contenuto; gestisce anche l'oggetto equipaggiato */
  if (save) {
    before = time(0);
    snprintf(path, sizeof path, "players/%s.dat", lower(ch->player.name));
    do_save(ch, (char *)"", 0);
    saved = stat(path, &st) == 0 && st.st_mtime >= before;
  }
  add_extra("saved=%d", saved);
  jw_raw(w, "{\"name\":");
  jw_str_latin1(w, ch->player.name);
  jw_raw(w, ",\"removed\":true,\"destroyed\":");
  jw_int(w, destroyed);
  jw_raw(w, ",\"saved\":");
  jw_raw(w, saved ? "true" : "false");
  jw_raw(w, ",\"warnings\":[");
  if (save && !saved)
    jw_raw(w, "\"save_failed\"");
  jw_raw(w, "]}");
  return 0;
}

/* ---------------------------------------------------------------- tabella dei comandi */

struct cmddef {
  const char *name;
  int write; /* 0 = classe read, 1 = classe write */
  int (*fn)(struct req *, struct jw *);
};

static const struct cmddef CMDS[] = {
    {"ping", 0, cmd_ping},         {"info", 0, cmd_info},         {"who", 0, cmd_who},
    {"player.get", 0, cmd_player_get}, {"zone.list", 0, cmd_zone_list}, {"player.set", 1, cmd_player_set},
    {"zone.reset", 1, cmd_zone_reset}, {"load.mob", 1, cmd_load_mob}, {"load.obj", 1, cmd_load_obj},
    {"echo", 1, cmd_echo},         {"player.inventory", 0, cmd_player_inventory}, {"obj.get", 0, cmd_obj_get},
    {"obj.set", 1, cmd_obj_set},   {"obj.remove", 1, cmd_obj_remove}};
#define NCMDS ((int)(sizeof CMDS / sizeof CMDS[0]))

static const struct cmddef *find_cmd(const char *name)
{
  for (int i = 0; i < NCMDS; i++)
    if (strcmp(CMDS[i].name, name) == 0)
      return &CMDS[i];
  return 0;
}

/* ---------------------------------------------------------------- connessioni */

static void conn_close(struct conn *c)
{
  if (c->fd >= 0)
    close(c->fd);
  c->fd = -1;
}

static int conn_flush(struct conn *c)
{
  while (c->outoff < c->outlen) {
    ssize_t n = send(c->fd, c->out + c->outoff, (size_t)(c->outlen - c->outoff), MSG_NOSIGNAL | MSG_DONTWAIT);
    if (n < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
        return 0;
      return -1;
    }
    c->outoff += (int)n;
  }
  c->outoff = c->outlen = 0;
  return 0;
}

/* accoda una riga di risposta; se non entra il client non sta leggendo: connessione chiusa */
static void conn_send(struct conn *c, const char *line, int len)
{
  if (c->fd < 0)
    return;
  if (c->outoff > 0 && c->outoff == c->outlen)
    c->outoff = c->outlen = 0;
  if (c->outlen + len + 1 > LC_OUT_SIZE) {
    glog("conn %d: coda di uscita piena, chiusa", c->id);
    conn_close(c);
    return;
  }
  memcpy(c->out + c->outlen, line, (size_t)len);
  c->outlen += len;
  c->out[c->outlen++] = '\n';
  if (conn_flush(c) < 0)
    conn_close(c);
}

static void write_id(struct jw *w, const struct jdoc *doc, const struct jnode *id)
{
  (void)doc;
  if (!id)
    jw_raw(w, "null");
  else if (id->type == J_INT)
    jw_int(w, id->i);
  else
    jw_str(w, id->s);
}

static void send_error(struct conn *c, const struct jdoc *doc, const struct jnode *id)
{
  struct jw w;
  jw_init(&w, g_resp, sizeof g_resp);
  jw_raw(&w, "{\"id\":");
  write_id(&w, doc, id);
  jw_raw(&w, ",\"ok\":false,\"error\":{\"code\":");
  jw_str(&w, g_code);
  jw_raw(&w, ",\"message\":");
  jw_str(&w, g_msg);
  if (g_eparams[0]) {
    jw_raw(&w, ",\"params\":");
    jw_raw(&w, g_eparams);
  }
  jw_raw(&w, "}}");
  conn_send(c, g_resp, w.len);
}

static int valid_id(const struct jnode *id)
{
  if (id->type == J_INT)
    return id->i >= 0 && id->i <= 9007199254740991LL;
  if (id->type == J_STR) {
    size_t n = strlen(id->s);
    if (n == 0 || n > 64)
      return 0;
    for (size_t i = 0; i < n; i++)
      if ((unsigned char)id->s[i] < 0x20 || (unsigned char)id->s[i] > 0x7e)
        return 0;
    return 1;
  }
  return 0;
}

static int valid_cmd_name(const char *s)
{
  size_t n = strlen(s);
  if (n == 0 || n > 32)
    return 0;
  for (size_t i = 0; i < n; i++)
    if (!(islower((unsigned char)s[i]) || (s[i] == '.' && i > 0 && i + 1 < n && s[i - 1] != '.')))
      return 0;
  return 1;
}

static void emit_hello(struct jw *w)
{
  jw_raw(w, "{\"protocol\":1,\"mud\":{\"kind\":\"dikumod\",\"name\":\"LeU\",\"version\":");
  jw_str(w, VERSION);
  jw_raw(w, ",\"module\":\"" LC_VERSION "\"},\"limits\":{\"max_line\":" );
  jw_int(w, LC_MAX_LINE);
  jw_raw(w, ",\"max_response\":");
  jw_int(w, LC_MAX_RESP);
  jw_raw(w, ",\"max_pending\":");
  jw_int(w, LC_MAX_PENDING);
  jw_raw(w, ",\"request_timeout_ms\":2000,\"max_text\":");
  jw_int(w, LC_MAX_TEXT);
  jw_raw(w, "},\"features\":[\"inventory\"],\"commands\":{");
  for (int i = 0, first = 1; i < NCMDS; i++) {
    if (CMDS[i].write && !L.write_enabled)
      continue;
    if (!first)
      jw_char(w, ',');
    first = 0;
    jw_str(w, CMDS[i].name);
    jw_raw(w, CMDS[i].write ? ":{\"class\":\"write\"" : ":{\"class\":\"read\"");
    if (strcmp(CMDS[i].name, "player.get") == 0 || strcmp(CMDS[i].name, "player.set") == 0) {
      jw_raw(w, ",\"fields\":");
      emit_field_names(w, CMDS[i].write);
    }
    jw_char(w, '}');
  }
  jw_raw(w, "}}");
}

static int do_hello(struct conn *c, const struct jdoc *doc, const struct jnode *params, struct jw *w, long long now)
{
  static const char *const keys[] = {"protocols", "token", "client", "actor", 0};
  const char *token = 0, *actor = 0, *client = 0;
  const struct jnode *prot, *p;
  int ok = 0;
  if (now < L.lock_until_ms)
    return EP("rate_limited", "troppi tentativi di autenticazione", "{\"retry_after_ms\":%lld}", L.lock_until_ms - now);
  if (!params || check_keys(doc, params, keys) < 0 || p_str(doc, params, "token", 1, &token) < 0)
    return -1;
  if (!token_equal(token, (int)strlen(token), L.token, L.toklen)) {
    c->fails++;
    if (now - L.fail_window_start_ms > 60000) {
      L.fail_window_start_ms = now;
      L.fail_window_count = 0;
    }
    if (++L.fail_window_count > 10)
      L.lock_until_ms = now + 30000;
    if (c->fails >= 3)
      c->close_after = 1;
    return E("auth_failed", "autenticazione fallita");
  }
  if (p_str(doc, params, "actor", 0, &actor) < 0 || p_str(doc, params, "client", 0, &client) < 0)
    return -1;
  if ((actor && strlen(actor) > 64) || (client && strlen(client) > 64))
    return E("bad_params", "actor/client troppo lunghi");
  prot = json_get(doc, params, "protocols");
  if (!prot || prot->type != J_ARR)
    return EP("bad_params", "protocols deve essere un array", "{\"field\":\"protocols\"}");
  for (p = json_child(doc, prot); p; p = json_next(doc, p))
    if (p->type == J_INT && p->i == LC_PROTOCOL)
      ok = 1;
  if (!ok)
    return EP("protocol_unsupported", "nessuna versione in comune", "{\"supported\":[1]}");
  c->authed = 1;
  sanitize(c->actor, sizeof c->actor, actor ? actor : "-", 0);
  emit_hello(w);
  return 0;
}

static void handle_line(struct conn *c, char *line, int len)
{
  const char *perr = 0;
  const struct jnode *root, *id, *cmdn, *params;
  const struct cmddef *cd;
  struct jw R, W;
  struct req rq;
  long long now = now_ms();
  int rc, pending = 0;
  static const char *const topkeys[] = {"id", "cmd", "params", 0};

  g_target[0] = g_extra[0] = 0;
  if (len > 0 && line[len - 1] == '\r')
    len--;
  if (len == 0)
    return;
  if (json_parse(&g_doc, line, len, &perr) < 0) {
    E("bad_json", perr);
    send_error(c, &g_doc, 0);
    return;
  }
  root = &g_doc.nodes[0];
  id = json_get(&g_doc, root, "id");
  if (root->type != J_OBJ || !id || !valid_id(id)) {
    E("bad_request", "richiesta senza id valido");
    send_error(c, &g_doc, 0);
    return;
  }
  cmdn = json_get(&g_doc, root, "cmd");
  params = json_get(&g_doc, root, "params");
  if (!cmdn || cmdn->type != J_STR || !valid_cmd_name(cmdn->s) || (params && params->type != J_OBJ) ||
      check_keys(&g_doc, root, topkeys) < 0) {
    E("bad_request", "richiesta malformata");
    send_error(c, &g_doc, id);
    return;
  }
  /* richieste ancora in attesa nel buffer */
  for (int i = 0; i < c->inlen; i++)
    if (c->in[i] == '\n')
      pending++;
  if (!take(&c->rate, LC_RATE_CONN, now) || !take(&L.global, LC_RATE_GLOBAL, now)) {
    EP("rate_limited", "troppe richieste", "{\"retry_after_ms\":100}");
    send_error(c, &g_doc, id);
    return;
  }
  if (pending >= LC_MAX_PENDING) {
    E("busy", "troppe richieste in coda");
    send_error(c, &g_doc, id);
    return;
  }
  c->last_ms = now;
  jw_init(&R, g_result, sizeof g_result);
  rq.c = c;
  rq.doc = &g_doc;
  if (strcmp(cmdn->s, "hello") == 0) {
    if (c->authed) {
      E("bad_request", "hello gia' eseguito");
      send_error(c, &g_doc, id);
      return;
    }
    rc = do_hello(c, &g_doc, params, &R, now);
    audit(c, "hello", rc < 0 ? g_code : "ok");
  } else if (!c->authed) {
    E("auth_required", "autenticazione richiesta");
    send_error(c, &g_doc, id);
    return;
  } else {
    cd = find_cmd(cmdn->s);
    if (!cd) {
      E("unknown_command", "comando sconosciuto");
      rc = -1;
    } else if (cd->write && !L.write_enabled) {
      E("command_disabled", "comando disattivato");
      rc = -1;
    } else if (cd->write && L.audit_fd < 0) {
      E("unavailable", "audit non disponibile: scritture sospese");
      rc = -1;
    } else if (params) {
      rq.params = params;
      rc = cd->fn(&rq, &R);
    } else {
      /* parametri assenti = oggetto vuoto: si usa la radice priva di figli temporaneamente */
      static struct jdoc empty;
      empty.count = 1;
      empty.nodes[0].type = J_OBJ;
      empty.nodes[0].first = empty.nodes[0].next = -1;
      empty.nodes[0].n = 0;
      empty.nodes[0].key = 0;
      empty.nodes[0].s = 0;
      rq.doc = &empty;
      rq.params = &empty.nodes[0];
      rc = cd->fn(&rq, &R);
    }
    if (rc == 0 && R.over) {
      E("internal", "risposta troppo grande");
      rc = -1;
    }
    if (cd && (cd->write || rc < 0 || strcmp(cd->name, "player.get") == 0 || strcmp(cd->name, "who") == 0 || 1))
      audit(c, cmdn->s, rc < 0 ? g_code : "ok");
  }
  if (rc < 0) {
    send_error(c, &g_doc, id);
    return;
  }
  jw_init(&W, g_resp, sizeof g_resp);
  jw_raw(&W, "{\"id\":");
  write_id(&W, &g_doc, id);
  jw_raw(&W, ",\"ok\":true,\"result\":");
  jw_raw(&W, g_result);
  jw_char(&W, '}');
  if (W.over) {
    E("internal", "risposta troppo grande");
    send_error(c, &g_doc, id);
    return;
  }
  conn_send(c, g_resp, W.len);
}

/* estrae e serve le righe complete nel buffer; ritorna il numero di richieste servite */
static int serve_lines(struct conn *c, int *budget, long long deadline_us)
{
  int served = 0;
  while (c->fd >= 0 && !c->close_after && c->inlen > 0 && *budget > 0) {
    int scan = c->inlen < LC_MAX_LINE + 2 ? c->inlen : LC_MAX_LINE + 2;
    char *nl = (char *)memchr(c->in, '\n', (size_t)scan);
    int linelen;
    if (!nl) {
      if (c->inlen >= LC_MAX_LINE + 2) {
        E("line_too_long", "riga troppo lunga");
        send_error(c, &g_doc, 0);
        c->close_after = 1;
      }
      break;
    }
    linelen = (int)(nl - c->in);
    if (linelen > LC_MAX_LINE + 1) { /* + eventuale \r */
      E("line_too_long", "riga troppo lunga");
      send_error(c, &g_doc, 0);
      c->close_after = 1;
      break;
    }
    c->in[linelen] = 0;
    /* la riga va copiata fuori dal buffer: handle_line conta i '\n' rimasti in c->in */
    {
      char tmp[LC_MAX_LINE + 2];
      memcpy(tmp, c->in, (size_t)linelen);
      memmove(c->in, c->in + linelen + 1, (size_t)(c->inlen - linelen - 1));
      c->inlen -= linelen + 1;
      handle_line(c, tmp, linelen);
    }
    served++;
    (*budget)--;
    if (now_us() > deadline_us)
      *budget = 0;
  }
  return served;
}

static void accept_new(void)
{
  for (;;) {
    int fd = accept4(L.listen_fd, 0, 0, SOCK_NONBLOCK | SOCK_CLOEXEC);
    struct ucred cred;
    socklen_t cl = sizeof cred;
    struct conn *c = 0;
    int active = 0;
    if (fd < 0)
      return;
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &cl) < 0 || ((int)cred.uid != (int)geteuid() && (int)cred.uid != L.allow_uid)) {
      glog("connessione rifiutata (uid %d)", fd >= 0 ? (int)cred.uid : -1);
      close(fd);
      continue;
    }
    for (int i = 0; i < LC_MAX_CONNS; i++) {
      if (L.conns[i].fd >= 0)
        active++;
      else if (!c)
        c = &L.conns[i];
    }
    if (!c || active >= L.max_conn) {
      static const char msg[] = "{\"id\":null,\"ok\":false,\"error\":{\"code\":\"too_many_connections\",\"message\":\"troppe connessioni\"}}\n";
      send(fd, msg, sizeof msg - 1, MSG_NOSIGNAL | MSG_DONTWAIT);
      close(fd);
      continue;
    }
    memset(c, 0, sizeof *c);
    c->fd = fd;
    c->id = ++L.next_conn_id;
    c->uid = (int)cred.uid;
    c->pid = (int)cred.pid;
    c->accepted_ms = c->last_ms = now_ms();
  }
}

void livectl_poll(void)
{
  struct pollfd pfd[LC_MAX_CONNS + 1];
  int map[LC_MAX_CONNS + 1], np = 0, budget = LC_MAX_PER_TICK;
  long long start = now_us(), deadline = start + LC_TICK_BUDGET_US, now = now_ms();

  if (!L.active)
    return;
  L.ticks++;
  pfd[np].fd = L.listen_fd;
  pfd[np].events = POLLIN;
  map[np++] = -1;
  for (int i = 0; i < LC_MAX_CONNS; i++) {
    struct conn *c = &L.conns[i];
    if (c->fd < 0)
      continue;
    pfd[np].fd = c->fd;
    pfd[np].events = (short)(POLLIN | (c->outlen > c->outoff ? POLLOUT : 0));
    map[np++] = i;
  }
  if (poll(pfd, (nfds_t)np, 0) > 0) {
    for (int k = 0; k < np; k++) {
      struct conn *c;
      if (!pfd[k].revents)
        continue;
      if (map[k] < 0) {
        accept_new();
        continue;
      }
      c = &L.conns[map[k]];
      if (pfd[k].revents & (POLLERR | POLLNVAL)) {
        conn_close(c);
        continue;
      }
      if ((pfd[k].revents & POLLOUT) && conn_flush(c) < 0) {
        conn_close(c);
        continue;
      }
      if (pfd[k].revents & (POLLIN | POLLHUP)) {
        int room = LC_IN_SIZE - c->inlen;
        if (room > 0 && !c->close_after) {
          ssize_t n = recv(c->fd, c->in + c->inlen, (size_t)room, MSG_DONTWAIT);
          if (n > 0)
            c->inlen += (int)n;
          else if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
            conn_close(c);
            continue;
          }
        }
      }
    }
  }
  for (int i = 0; i < LC_MAX_CONNS; i++) {
    struct conn *c = &L.conns[i];
    if (c->fd < 0)
      continue;
    serve_lines(c, &budget, deadline);
    if (c->fd < 0)
      continue;
    if (c->close_after && c->outoff >= c->outlen) {
      conn_close(c);
      continue;
    }
    if ((!c->authed && now - c->accepted_ms > LC_HELLO_TIMEOUT_MS) || (now - c->last_ms > LC_IDLE_TIMEOUT_MS))
      conn_close(c);
  }
}

/* ---------------------------------------------------------------- avvio e chiusura */

void livectl_shutdown(void)
{
  if (!L.active)
    return;
  for (int i = 0; i < LC_MAX_CONNS; i++)
    conn_close(&L.conns[i]);
  if (L.listen_fd >= 0)
    close(L.listen_fd);
  if (L.owns_socket)
    unlink(L.sock_path);
  if (L.audit_fd >= 0)
    close(L.audit_fd);
  L.active = 0;
}

static void parse_deny(const char *s)
{
  while (*s && L.ndeny < LC_MAX_DENY) {
    char *end;
    long lo = strtol(s, &end, 10), hi;
    if (end == s)
      break;
    hi = lo;
    if (*end == '-') {
      s = end + 1;
      hi = strtol(s, &end, 10);
    }
    L.deny[L.ndeny].lo = lo;
    L.deny[L.ndeny++].hi = hi;
    s = *end == ',' ? end + 1 : end;
    if (end == s && *s)
      break;
  }
}

static int open_listener(void)
{
  struct sockaddr_un sa;
  struct stat st;
  mode_t old;
  int fd;
  if (strlen(L.sock_path) >= sizeof sa.sun_path)
    return -1;
  if (lstat(L.sock_path, &st) == 0) {
    int probe;
    if (!S_ISSOCK(st.st_mode)) {
      glog("%s esiste e non e' un socket: canale non attivato", L.sock_path);
      return -1;
    }
    probe = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    memset(&sa, 0, sizeof sa);
    sa.sun_family = AF_UNIX;
    strcpy(sa.sun_path, L.sock_path);
    if (probe >= 0 && (connect(probe, (struct sockaddr *)&sa, sizeof sa) == 0 || errno == EAGAIN)) {
      close(probe);
      glog("un'altra istanza usa gia' %s: canale non attivato", L.sock_path);
      return -1;
    }
    if (probe >= 0)
      close(probe);
    unlink(L.sock_path);
  }
  fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  if (fd < 0)
    return -1;
  memset(&sa, 0, sizeof sa);
  sa.sun_family = AF_UNIX;
  strcpy(sa.sun_path, L.sock_path);
  old = umask(0177);
  if (bind(fd, (struct sockaddr *)&sa, sizeof sa) < 0 || listen(fd, 4) < 0) {
    umask(old);
    glog("bind/listen su %s fallito (%s)", L.sock_path, strerror(errno));
    close(fd);
    return -1;
  }
  umask(old);
  L.owns_socket = 1;
  return fd;
}

void livectl_init(void)
{
  const char *e;
  memset(&L, 0, sizeof L);
  L.listen_fd = L.audit_fd = -1;
  for (int i = 0; i < LC_MAX_CONNS; i++)
    L.conns[i].fd = -1;
  L.allow_uid = -1;

  e = getenv("LIVECTL_SOCKET");
  if (!e || !*e)
    return; /* canale non configurato */
  if (strlen(e) >= sizeof L.sock_path) {
    glog("LIVECTL_SOCKET troppo lungo (max %d): canale non attivato", (int)sizeof L.sock_path - 1);
    return;
  }
  snprintf(L.sock_path, sizeof L.sock_path, "%s", e);
  if (access("livectl.disable", F_OK) == 0) {
    glog("livectl.disable presente: canale non attivato");
    return;
  }
  e = getenv("LIVECTL_TOKEN");
  if (e) {
    L.toklen = (int)strlen(e);
    if (L.toklen >= LC_TOKEN_MIN && L.toklen <= LC_TOKEN_MAX)
      memcpy(L.token, e, (size_t)L.toklen + 1);
    else
      L.toklen = 0;
    unsetenv("LIVECTL_TOKEN"); /* il segreto non resta nell'ambiente del processo */
  }
  if (L.toklen == 0) {
    glog("LIVECTL_TOKEN mancante o di lunghezza non valida (%d..%d): canale non attivato", LC_TOKEN_MIN, LC_TOKEN_MAX);
    return;
  }
  for (const char *p = L.token; *p; p++)
    if ((unsigned char)*p <= 0x20 || (unsigned char)*p > 0x7e) {
      glog("LIVECTL_TOKEN contiene caratteri non ammessi: canale non attivato");
      memset(L.token, 0, sizeof L.token);
      return;
    }
  if (L.sock_path[0] != '/') {
    glog("LIVECTL_SOCKET deve essere un percorso assoluto: canale non attivato");
    return;
  }
  e = getenv("LIVECTL_CLASSES");
  L.write_enabled = e && strstr(e, "write") != 0;
  e = getenv("LIVECTL_MAX_CONN");
  L.max_conn = e ? atoi(e) : 4;
  if (L.max_conn < 1 || L.max_conn > LC_MAX_CONNS)
    L.max_conn = 4;
  e = getenv("LIVECTL_ALLOW_UID");
  if (e)
    L.allow_uid = atoi(e);
  parse_deny(getenv("LIVECTL_DENY_OBJ") ? getenv("LIVECTL_DENY_OBJ") : "150-199,1600,5311,13702,21113,21117,21120-21122");
  e = getenv("LIVECTL_AUDIT");
  L.audit_fd = open(e && *e ? e : "livectl.audit", O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
  if (L.audit_fd < 0)
    glog("audit non apribile (%s): le scritture resteranno disattivate", strerror(errno));
  L.listen_fd = open_listener();
  if (L.listen_fd < 0) {
    if (L.audit_fd >= 0)
      close(L.audit_fd);
    L.audit_fd = -1;
    return;
  }
  L.active = 1;
  atexit(livectl_shutdown);
  glog("canale attivo su %s (classi: read%s)", L.sock_path, L.write_enabled ? ",write" : "");
}

#endif /* LIVECTL */
