/*
 * livectl_json.h - parser/serializzatore JSON minimo a limiti fissi per il canale livectl.
 * Nessuna dipendenza dal gioco (si compila e si fuzza da solo). Nessun malloc: tutto in strutture di dimensione fissa.
 * Solo interi, stringhe UTF-8 valide, oggetti (chiavi uniche), array, true/false/null.
 */
#ifndef LIVECTL_JSON_H
#define LIVECTL_JSON_H

#define LC_MAX_LINE   4096   /* lunghezza massima di una riga di richiesta */
#define LC_MAX_NODES  160
#define LC_MAX_DEPTH  4
#define LC_MAX_KEYS   32
#define LC_MAX_ARRAY  32
#define LC_MAX_STR    512

enum { J_NULL = 0, J_BOOL, J_INT, J_STR, J_OBJ, J_ARR };

struct jnode {
  int type;
  long long i;          /* J_INT, J_BOOL (0/1) */
  const char *s;        /* J_STR: stringa UTF-8 NUL-terminata (dentro jdoc.buf) */
  const char *key;      /* chiave nel padre oggetto */
  int first, next;      /* indici: primo figlio, fratello successivo (-1 = nessuno) */
  int n;                /* numero di figli */
};

struct jdoc {
  struct jnode nodes[LC_MAX_NODES];
  int count;
  char buf[LC_MAX_LINE + 1]; /* contiene chiavi e stringhe decodificate */
  int used;
};

/* 0 = ok (radice = nodes[0]); altrimenti -1 e *err = motivo (stringa statica) */
int json_parse(struct jdoc *d, const char *line, int len, const char **err);
const struct jnode *json_get(const struct jdoc *d, const struct jnode *obj, const char *key);
const struct jnode *json_child(const struct jdoc *d, const struct jnode *n);   /* primo figlio o NULL */
const struct jnode *json_next(const struct jdoc *d, const struct jnode *n);    /* fratello o NULL */

/* Scrittura su buffer limitato: se si supera la capacita' resta over=1 e non si scrive piu' nulla. */
struct jw {
  char *p;
  int len, cap, over;
};
void jw_init(struct jw *w, char *buf, int cap);
void jw_raw(struct jw *w, const char *s);
void jw_char(struct jw *w, char c);
void jw_int(struct jw *w, long long v);
void jw_str(struct jw *w, const char *utf8);     /* stringa JSON da UTF-8 (escape di " \ e controlli) */
void jw_str_latin1(struct jw *w, const char *s); /* idem da latin-1 (la codifica del gioco); s puo' essere NULL */

/* Conversioni di testo */
int utf8_to_latin1(const char *in, char *out, int cap); /* >=0 lunghezza; -1 non rappresentabile/invalido; -2 troppo lungo */
#endif
