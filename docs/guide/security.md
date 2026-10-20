# Sicurezza e limiti noti

## Header di sicurezza

Ogni risposta dell'app (API, SPA e `/docs`) porta, se non li ha gia' impostati qualcun altro:

| Header | Valore |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | politica descritta qui di seguito |

La CSP e' definita in `pachimudeditor.common.http_guard`:

- **API e SPA**: `default-src 'self'`; script solo dallo stesso sito (la SPA Quasar non usa script inline);
  stili `'self'` e `'unsafe-inline'` (Quasar imposta `style` inline) piu' `fonts.googleapis.com`; font `'self'`, `data:` e
  `fonts.gstatic.com` (il font Geist e' caricato da Google Fonts dai pacchetti `@ilpachi`); immagini `'self'`, `data:`, `blob:`;
  `connect-src 'self'`; `object-src 'none'`; `frame-ancestors 'none'`.
- **`/docs*` (Swagger UI di FastAPI)**: come sopra ma con `cdn.jsdelivr.net` per script e stili, script inline e
  l'icona da `fastapi.tiangolo.com`. Resta pubblica come prima; se non serve, bloccala dal reverse proxy.

HSTS non e' impostato dall'app: va configurato sul reverse proxy che termina TLS. Il test E2E `e2e/tests/security.test.ts`
verifica nel browser che SPA e `/docs` funzionino senza violazioni CSP.

## Limite di richieste sugli endpoint costosi

Le conversioni (`POST /api/convert/preview` e `/run`) e l'import di zone (`POST /api/transfer/zones/import`) sono limitati
per indirizzo client con un contatore a finestra fissa nella cache di pachifast (in memoria del processo; condivisa tra
worker solo con `cache_url` Redis). Oltre il limite: `429` con `Retry-After` e codice `auth.rate_limited`.

| Variabile | Default | Significato |
| --- | --- | --- |
| `WEBEDITOR_HEAVY_RATE_LIMIT` | `60` | richieste per finestra e per indirizzo; `0` = nessun limite |
| `WEBEDITOR_HEAVY_RATE_WINDOW` | `60` | durata della finestra in secondi |

pachifast offre un limite analogo solo per login/registrazione/MFA (`auth_rate_limit`, spento di default): non copre gli
endpoint dell'editor, per questo il limite sopra e' dell'editor. Dietro un reverse proxy avvia uvicorn con
`--proxy-headers`, altrimenti tutti i client condividono l'indirizzo del proxy e quindi un solo budget.

## Decisioni aperte (lasciate all'utente)

Le due questioni seguenti sono limiti noti, **non** modificati: richiedono una scelta di prodotto.

### Modello dei permessi per utente

*Oggi*: ogni utente autenticato che non sia superuser puo' scrivere in **ogni** mondo configurato (le uniche barriere sono
l'autenticazione e il flag `read_only` del mondo, uguale per tutti). Non esistono permessi per mondo ne' per risorsa.

Alternative:

1. **Permessi pachifast per mondo** (es. `world.<id>.write`): si assegnano ai gruppi con i meccanismi di pachifast e un
   controllo nelle rotte di scrittura; e' la via piu' piccola, ma serve gestire i permessi alla creazione dei mondi.
2. **Elenco utenti/gruppi per mondo nella configurazione** (`webeditor_worlds[].writers`): niente DB, ma modifiche solo da file.
3. **Solo superuser scrivono** e gli altri leggono: semplicissimo, ma toglie la scrittura a chi oggi la usa.
4. Lasciare cosi' se gli utenti sono pochi e fidati (situazione attuale).

### Token in `localStorage`

*Oggi*: la SPA (tramite `@ilpachi/pachifastquasar`) conserva i token di accesso e di refresh nel `localStorage` del
browser. Un XSS potrebbe leggerli; la CSP stretta sopra riduce il rischio (niente script inline o di terzi) ma non lo elimina.

Alternative:

1. **Cookie `HttpOnly` + `SameSite=Strict`** per il refresh token (e access token solo in memoria): il JS non puo' leggerli,
   richiede modifiche a pachifast (emissione/lettura dei cookie) e una protezione CSRF.
2. **Access token solo in memoria** e refresh in cookie: come sopra, con ricarica silenziosa dell'access token.
3. **`sessionStorage`**: il token non sopravvive alla chiusura della scheda, ma resta leggibile da un XSS.
4. Lasciare cosi', accettando il rischio, con CSP e access token a vita breve.
