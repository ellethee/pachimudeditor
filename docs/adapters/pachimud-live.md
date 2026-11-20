# pachimud, canale live (`livectl`)

Il gioco pachimud espone il protocollo `livectl` v1 ([specifica](../backend/live-control-protocol.md), [rotte](../backend/contract-live.md)) con un componente asyncio nello stesso processo
del gioco (ogni comando e' atomico rispetto ai comandi dei giocatori). Il canale e' **opzionale**: senza, l'editor lavora solo sui file.

## Configurazione

Lato gioco (`pachimud.yaml`):

```yaml
livectl:
  enabled: true
  socket_path: /percorso/assoluto/pachimud.sock   # socket Unix, umask 0177, SO_PEERCRED sull'UID
  allow_write: false                              # true abilita zone.reset e zone.reload
  max_connections: 4
```

Il token e' la variabile d'ambiente `LIVECTL_TOKEN` del gioco (almeno 32 caratteri; letta all'avvio e rimossa dall'ambiente). Senza token il canale non parte e il gioco si avvia lo stesso.

Lato editor (`params.live` del mondo, stessa forma di [dikumod](dikumod-live.md)): `socket` (percorso assoluto), `token_env` (il **nome** della variabile, il cui valore sta nel `.env` della cartella di lavoro
o nell'ambiente: mai il token nel yaml), `timeout_ms` (200-60000, default 3000), `enabled: false` per spegnere il canale senza toglierlo. Parametri incoerenti sono un errore all'avvio; un socket assente o un token non impostato no
(stato `unreachable` / `token_missing`). Con `params.live` il mondo dichiara la capability `supports_live`; `supports_live_inventory` resta falsa (il gioco non ha la feature `inventory`).

## Cosa offre

Le funzioni dipendono da `hello.commands` del gioco (capability discovery):

| Funzione | Comando | Classe |
| --- | --- | --- |
| stato, giocatori connessi, valori correnti in sola lettura | `ping`, `info`, `who`, `player.get` | `read` |
| zone come le vede il gioco (`index == num ==` vnum) | `zone.list` | `read` |
| istanze in memoria per stanza o prototipo | `instances.list` | `read` |
| reset di una zona | `zone.reset` | `write` |
| rilettura dei YAML di una zona e nuovo reset | `zone.reload` | `write` |

Non esistono `player.set`, `load.mob`, `load.obj`, `echo` e l'inventario: le rotte relative rispondono 409 (`worldlive.command_disabled`) e la UI non le mostra.
Le scritture (`zone.reset`, `zone.reload`) richiedono anche un mondo non `read_only` lato editor e `allow_write: true` lato gioco.

Differenze di formato rispetto a Diku Modificato (gestite dai DTO live): `race` stringa nel `who`, `levels` con la sola classe, `sex`/`position` numerici, `zone.list` con `bottom`/`top`, nessun `move`.

## Ricaricare una zona dopo la modifica

Il gioco non ricarica a caldo. Dopo aver salvato una zona nell'editor (che scrive i YAML) si puo' chiedere al gioco di rileggerla:

- **UI**: dettaglio zona -> «Ricarica nel gioco» (visibile solo a un superuser, con canale connesso, `allow_write` attivo e `zone.reload` dichiarato).
- **API**: `POST /api/world/live/zones/reload` `{"vnum": 10}`; **CLI**: `pachimudeditor live --world pachimud zone reload 10`.

`zone.reload` ricrea mob e oggetti della zona; i giocatori restano nella stanza se esiste ancora. Se un YAML non e' valido il gioco risponde `reload_failed` (l'editor: 409 `worldlive.reload_failed` con messaggio it/en) e la zona **resta com'era**: stanze, prototipi e reset vengono ripristinati e mob e oggetti vivi non cambiano. Correggere i file (`worlds check`) e riprovare.

## Contenuti: controllo e ricarica

Con `content.validate` (lettura) e `content.reload` (scrittura, serve `allow_write`) il gioco controlla e rilegge a caldo razze, classi, skill, tabelle, social e cataloghi:

- **UI**: nelle pagine Skill, Social, Tabelle e Cataloghi e testi, «Controlla i file» e «Ricarica nel gioco» (visibili solo a un superuser con canale connesso e i comandi dichiarati; il secondo
  anche con `allow_write` e mondo non in sola lettura). Dopo ogni salvataggio il controllo parte da solo; i problemi (gravita', codice, messaggio, file:riga) restano in un pannello. Senza canale la barra ricorda che le modifiche valgono al riavvio.
- **API**: `GET /api/world/live/content/validate[?strict=true]` e `POST /api/world/live/content/reload` `{"kind": "skills"}` (`races`, `classes`, `skills`, `tables`, `socials`, `locales`, `all`).
- **CLI**: `pachimudeditor live --world pachimud content validate [--strict]` e `content reload [kind]`.

La ricarica e' **tutto o niente**: se un file non si legge (YAML, campi non validi) il gioco risponde `reload_failed`, l'editor 409 `worldlive.content_reload_failed` con i problemi in `detail[0].params.issues`,
e il gioco resta com'era. Gli errori semantici (id inesistenti, segnaposto diversi nei cataloghi, effetti sconosciuti) **non** bloccano la ricarica: li riporta `content.validate`. Limiti del gioco: non ricarica i giocatori
connessi (tengono razza e classe vecchie fino al rientro), le zone (usare `zone.reload`) e gli hook Python.

## Istanze live

`GET /api/world/live/instances?roomVnum=...|mobVnum=...|objVnum=...|zoneVnum=...` (CLI: `pachimudeditor live --world pachimud instances --room 1001`, o `--mob`, `--obj`, `--zone`) elenca le istanze in RAM
(`instanceId`, `kind`, `vnum`, `roomVnum`); per oggetti e stanze solo quelli a terra; per la zona i suoi mob e gli oggetti a terra nelle sue stanze. Nel dettaglio zona, con il canale connesso e `instances.list` dichiarato, una scheda mostra quanti mob e oggetti vivi ci sono (con aggiorna).

## Limiti noti

- Il canale non conosce i giocatori in login (`connecting` e `linkdead` sempre 0); `idle` e `invisible` sempre 0; `info` non ha `lag_us`.
- Il limite di richieste (20/s) e' per connessione.
- I giocatori del DB non hanno il badge «online» da questo canale (nessun collegamento ai giocatori su file, a differenza di dikumod).
