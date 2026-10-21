/*
 * Fuzz semplice del parser JSON del modulo (senza dipendenze dal gioco).
 *   g++ -std=gnu++98 -O1 -g -fsanitize=address,undefined -I.. fuzz/fuzz_json.c livectl_json.c -o fuzz_json && ./fuzz_json [iterazioni] [seed]
 * Mutazioni casuali di richieste valide, byte casuali, righe lunghissime, annidamenti profondi; ogni risultato "ok" e'
 * ricontrollato (puntatori dentro il buffer, figli coerenti). Esce con 0 se non ci sono crash ne' violazioni.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "livectl_json.h"

static const char *SEEDS[] = {
    "{\"id\":1,\"cmd\":\"hello\",\"params\":{\"protocols\":[1],\"token\":\"abc\",\"actor\":\"x\"}}",
    "{\"id\":\"a\",\"cmd\":\"player.set\",\"params\":{\"name\":\"Mario\",\"set\":{\"gold\":5,\"levels\":{\"warrior\":3}},\"save\":true}}",
    "{\"id\":2,\"cmd\":\"echo\",\"params\":{\"text\":\"ciao \\u00e8 \\ud83d\\ude00 \\\"x\\\"\",\"to\":{\"all\":true}}}",
    "[1,2,[3,[4,[5]]],{\"a\":null,\"b\":false}]",
    "{\"k\":-0,\"n\":-12345678901234567,\"s\":\"\xc3\xa8\xe2\x82\xac\"}",
};

static unsigned long long rs;
static unsigned rnd(void)
{
  rs = rs * 6364136223846793005ULL + 1442695040888963407ULL;
  return (unsigned)(rs >> 33);
}

static void check(const struct jdoc *d)
{
  for (int i = 0; i < d->count; i++) {
    const struct jnode *n = &d->nodes[i];
    if (n->type == J_STR && !(n->s >= d->buf && n->s < d->buf + sizeof d->buf))
      abort();
    if (n->key && !(n->key >= d->buf && n->key < d->buf + sizeof d->buf))
      abort();
    if (n->first >= d->count || n->next >= d->count)
      abort();
    if (n->type == J_STR && strlen(n->s) > LC_MAX_STR)
      abort();
  }
}

int main(int argc, char **argv)
{
  long iters = argc > 1 ? atol(argv[1]) : 200000;
  static char line[LC_MAX_LINE * 2];
  static struct jdoc d;
  long ok = 0;
  rs = argc > 2 ? strtoull(argv[2], 0, 10) : 12345;
  for (long it = 0; it < iters; it++) {
    const char *err = 0;
    int len;
    switch (rnd() % 6) {
    case 0: /* byte casuali */
      len = (int)(rnd() % 300);
      for (int i = 0; i < len; i++)
        line[i] = (char)rnd();
      break;
    case 1: { /* annidamento profondo / righe lunghe */
      int depth = (int)(rnd() % 3000);
      len = 0;
      for (int i = 0; i < depth && len < (int)sizeof line - 4; i++)
        line[len++] = (rnd() & 1) ? '[' : '{';
      break;
    }
    case 2: /* riga piu' lunga del limite */
      len = LC_MAX_LINE + 1 + (int)(rnd() % 500);
      memset(line, 'a', (size_t)len);
      line[0] = '"';
      break;
    default: { /* mutazioni di un seme */
      const char *sd = SEEDS[rnd() % (sizeof SEEDS / sizeof SEEDS[0])];
      len = (int)strlen(sd);
      memcpy(line, sd, (size_t)len);
      for (int m = (int)(rnd() % 6); m >= 0; m--) {
        int p = (int)(rnd() % (unsigned)len);
        switch (rnd() % 4) {
        case 0: line[p] = (char)rnd(); break;
        case 1: memmove(line + p, line + p + 1, (size_t)(len - p - 1)); len--; break;
        case 2:
          if (len < (int)sizeof line - 2) {
            memmove(line + p + 1, line + p, (size_t)(len - p));
            line[p] = (char)rnd();
            len++;
          }
          break;
        default: line[p] = "{}[]\",:\\ -0e."[rnd() % 14]; break;
        }
      }
    }
    }
    if (json_parse(&d, line, len, &err) == 0) {
      ok++;
      check(&d);
    } else if (!err) {
      abort();
    }
  }
  printf("fuzz_json: %ld iterazioni, %ld parse riusciti, nessun crash\n", iters, ok);
  return 0;
}
