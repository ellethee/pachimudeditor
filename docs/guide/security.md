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

Le conversioni (`POST /api/convert/preview` e `/run`) e l'import di zone (`POST /api/transfer/zones/import`) usano il
`rate_limit` di pachifast (`pachifast>=0.18`) come dipendenza di rotta: contatore a finestra fissa per **utente autenticato**
(ripiego: indirizzo IP, IPv6 come rete /64), con un solo budget (scope `heavy`) condiviso dalle tre rotte, nella cache di pachifast
(memoria del processo; condivisa tra worker solo con `cache.url` Redis). Le richieste non autenticate sono rifiutate (401) prima
del conteggio. Oltre il limite: `429` con `Retry-After`, codice `api.rate_limited` e header `X-RateLimit-Limit`/`-Remaining`/`-Reset`
(anche sulle risposte riuscite).

Configurazione con le impostazioni di pachifast (yaml o env):

| yaml (`rate_limit.`) | Env | Default dell'editor | Significato |
| --- | --- | --- | --- |
| `default` | `PACHIFAST_RATE_LIMIT_DEFAULT` | `60` | richieste per finestra e utente; `0` = nessun limite |
| `window_seconds` | `PACHIFAST_RATE_LIMIT_WINDOW_SECONDS` | `60` | durata della finestra in secondi |

pachifast lascia il limite spento; l'editor lo imposta a 60/60 s se non e' scritto. Gli env `WEBEDITOR_HEAVY_RATE_LIMIT` e
`WEBEDITOR_HEAVY_RATE_WINDOW` restano come **alias deprecati**: valgono solo se la chiave pachifast corrispondente non e' scritta.
Dietro un reverse proxy avvia uvicorn con `--proxy-headers` (`pachifast serve` lo fa), altrimenti i client anonimi condividono
l'indirizzo del proxy. Nota: il codice di errore e' passato da `auth.rate_limited` ad `api.rate_limited`.

## Sessione: refresh token in cookie HttpOnly

L'editor usa la modalita' cookie di pachifast (`auth.refresh_mode: cookie`, default dell'editor) e di `@ilpachi/pachifastquasar`
(`auth: { refreshMode: 'cookie' }`). Questo risolve la vecchia decisione aperta sui token nel `localStorage`:

- il **refresh token** (il segreto di lunga durata) e' un cookie `HttpOnly`, `SameSite=Lax`, `Path=/api/auth`: il JavaScript
  della pagina non lo legge (`document.cookie` non lo mostra) e non resta in nessuno storage;
- l'**access token** (breve) vive solo in memoria; a ogni caricamento la SPA fa un refresh silenzioso. Nel `localStorage` non
  c'e' nessun token; la sessione e' condivisa tra le schede tramite Web Lock e BroadcastChannel, e il logout in una scheda
  porta le altre al login;
- un refresh ripetuto entro `refresh_reuse_grace_seconds` col token appena ruotato (ricarica subito dopo una navigazione) risponde 200 con un nuovo `Set-Cookie` invece di 401: richiede **pachifast>=0.17.1**;
- **CSRF**: `refresh-token` e `logout` con il cookie richiedono l'header `X-Pachi-Auth: refresh` e, se presente, un `Origin`
  uguale all'host (o in `refresh_allowed_origins`); altrimenti `403 auth.csrf_rejected`. Il proxy deve inoltrare header e `Host`;
- `Secure` e' automatico su https; con un reverse proxy avvia uvicorn con `--proxy-headers`. `localhost` funziona in http,
  un IP di rete in http no.

**Rischio residuo**: uno script iniettato (XSS) non puo' piu' rubare la sessione, ma finche' la pagina e' aperta puo' usare
l'access token in memoria e chiamare l'API come l'utente. Restano quindi necessari la CSP stretta sopra e l'igiene delle
dipendenze. Verificato dai test E2E `e2e/tests/auth.test.ts`.

## Decisioni aperte (lasciate all'utente)

La questione seguente e' un limite noto, **non** modificato: richiede una scelta di prodotto.

### Modello dei permessi per utente

*Oggi*: ogni utente autenticato che non sia superuser puo' scrivere in **ogni** mondo configurato (le uniche barriere sono
l'autenticazione e il flag `read_only` del mondo, uguale per tutti). Non esistono permessi per mondo ne' per risorsa.

Alternative:

1. **Permessi pachifast per mondo** (es. `world.<id>.write`): si assegnano ai gruppi con i meccanismi di pachifast e un
   controllo nelle rotte di scrittura; e' la via piu' piccola, ma serve gestire i permessi alla creazione dei mondi.
2. **Elenco utenti/gruppi per mondo nella configurazione** (`webeditor_worlds[].writers`): niente DB, ma modifiche solo da file.
3. **Solo superuser scrivono** e gli altri leggono: semplicissimo, ma toglie la scrittura a chi oggi la usa.
4. Lasciare cosi' se gli utenti sono pochi e fidati (situazione attuale).
