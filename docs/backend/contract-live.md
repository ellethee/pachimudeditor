# Contratto backend: canale live (`/api/world/live`)

Introdotto con l'**SDK 1.5**. Porta all'editor il [canale di controllo live](live-control-protocol.md) (protocollo `livectl` v1) verso un MUD **acceso**:
giocatori connessi, stato del server e modifiche immediate senza fermare il gioco. Affianca i [giocatori su file](contract-players-files.md), non li sostituisce.
Stesse convenzioni di [contratto API](contract.md): auth Bearer, envelope `{success,message,data}`, camelCase, errori `detail[{loc,msg,type,code,params}]`,
mondo con `X-World`.

## Permessi e condizioni

| Condizione | Risposta |
| --- | --- |
| nessuna sessione | 401 |
| utente non superuser | 403 `access.superuser_required` (**tutte** le rotte, anche le letture) |
| mondo senza capability `supportsLive` | 409 `world.capability_missing` (`params.capability = supports_live`) |
| scrittura su mondo `read_only` | 409 `world.read_only` (le letture restano permesse) |

La capability `supportsLive` e' dichiarata da dikumod solo se `params.live` e' configurato e non `enabled: false`.

## Rotte

| Rotta | Esito |
| --- | --- |
| `GET /world/live/status` | `LiveStatus`: **sempre 200**, un MUD spento e' `state: unreachable`. Mai socket o token |
| `GET /world/live/who` | `LiveWho` `{players[], count, truncated}` (anche link morti: `state` `playing`/`linkdead`/`polymorph`) |
| `GET /world/live/info` | `LiveServerInfo` (uptime, giocatori, contatori del mondo) |
| `GET /world/live/zones` | `{zones[{index,num,name,top,lifespan,age,resetMode,started}]}`: le zone **come le vede il gioco** |
| `GET /world/live/players/{name}` | `{name,state,fields,editableFields}`: valori correnti **in memoria** |
| `PATCH /world/live/players/{name}` | body `{fields, save?=true, confirmImmortal?=false}` -> `{name,applied{campo:{old,new}},saved,warnings[]}` |
| `POST /world/live/zones/reset` | body `{zone}` oppure `{room}` (uno solo), `onlyIfEmpty?` -> `{zone,name,executed}` |
| `POST /world/live/load/mob`, `/load/obj` | body `{vnum, room}` oppure `{vnum, player}`, `count?` 1..10, `notify?` -> `{loaded[]}` |
| `POST /world/live/echo` | body `{text}` + **una** tra `all: true`, `player`, `room` -> `{recipients}` |

`fields` ha i nomi del protocollo: `gold`, `bankGold`, `exp`, `hit`, `mana`, `move`, `str`, `strAdd`, `int`, `wis`, `dex`, `con`, `chr`, `alignment`, `spellsToLearn`
e gli oggetti annidati `levels: {classe: livello}` e `conditions: {drunk|full|thirst: valore}`. Quelli accettati davvero dal MUD sono in `status.editableFields`
(un campo non dichiarato e' 422 `worldlive.bad_params`). Il nome di un giocatore deve essere `[A-Za-z][A-Za-z0-9_-]{0,19}` (altrimenti 404 senza interrogare il MUD).

**Immortali.** Promuovere una classe a un livello >= 51 (e maggiore dell'attuale) senza `confirmImmortal: true` e' rifiutato con 409
`worldlive.immortal_confirmation_required` e **nulla** viene modificato (neppure gli altri campi della richiesta); con la conferma la risposta ha
`warnings: ["immortal_level"]`. L'interfaccia mostra l'avvertenza («stai creando un immortale: avra' i poteri di un dio nel gioco») e invia il flag solo dopo la conferma.

**Scritture mai ritentate.** `PATCH`, `reset`, `load`, `echo` non si ripetono in automatico: dopo un timeout o una caduta della connessione la risposta e'
504 `worldlive.outcome_unknown` (l'operazione potrebbe essere stata eseguita: rileggere con `GET /players/{name}` o `/who` prima di ripetere).

## Errori

| HTTP | `code` | Quando (`params`) |
| --- | --- | --- |
| 404 | `worldlive.not_found` | giocatore non connesso, zona, stanza, vnum o nome non valido (`what`) |
| 409 | `worldlive.player_not_playing` / `worldlive.player_busy` | login, menu, link morto / trasformato o in un editor di testo |
| 409 | `worldlive.immortal_confirmation_required` | livello >= 51 senza conferma (`level`) |
| 409 | `worldlive.class_not_owned` | classe non posseduta (`class_name`) |
| 409 | `worldlive.zone_forbidden` | zona 0 |
| 409 | `worldlive.object_denied` | vnum nella deny-list del MUD (`vnum`) |
| 409 | `worldlive.forbidden_by_policy` | altra regola del MUD (`reason`) |
| 409 | `worldlive.command_disabled` | comando non dichiarato da `hello` (classe `write` spenta nel MUD) |
| 422 | `worldlive.value_out_of_range` | valore fuori intervallo (`field`, `min`, `max`) |
| 422 | `worldlive.bad_params` / `worldlive.unencodable_text` | richiesta rifiutata dal MUD / testo non rappresentabile (latin-1) |
| 429 | `worldlive.rate_limited` | troppe richieste (`retry_after_ms`) |
| 503 | `worldlive.unreachable` | MUD spento, socket assente o rifiutato |
| 503 | `worldlive.auth_failed` / `worldlive.token_missing` | token rifiutato / variabile d'ambiente non impostata |
| 503 | `worldlive.busy` / `worldlive.unavailable` | coda piena o connessioni esaurite / il MUD si sta spegnendo |
| 504 | `worldlive.timeout` | nessuna risposta a una lettura |
| 504 | `worldlive.outcome_unknown` | nessuna risposta a una scrittura dopo l'invio |
| 502 | `worldlive.protocol_error` / `worldlive.protocol_unsupported` | risposta inattesa o oltre i limiti / nessuna versione in comune |

I messaggi sono it/en; il token non compare in nessuna risposta, log o errore.

## `LiveStatus`

```json
{"state": "connected", "reachable": true, "code": null, "protocol": 1,
 "mud": {"kind": "dikumod", "name": "LeU", "version": "1.7.0 cdrom", "module": "livectl 0.1"},
 "classes": ["read", "write"], "commands": ["echo", "info", "ping", "player.get", "..."], "features": [],
 "editableFields": ["gold", "bankGold", "levels", "..."], "latencyMs": 3}
```

`state`: `connected`, `unreachable`, `auth_failed`, `token_missing`, `error`; se non e' `connected`, `code` e' il codice `worldlive.*` del motivo.

## Integrazione con i giocatori su file

Quando il canale risponde, per i mondi con `supportsLive`:

- `PlayerSummary.online` / `PlayerDetail.online` valgono `true` (connesso, anche a link caduto) o `false` (il canale risponde e non c'e'); `extra.liveState` = `playing|linkdead|polymorph`.
  Canale spento o non configurato: `null` come prima. L'elenco dei connessi (`who`) ha una cache di 2 secondi, anche per i fallimenti.
- `GET /world/players/status` risponde `serverRunning: true, detection: "live"` (il server e' acceso con certezza).
- Scrivere **su file** un giocatore connesso richiede `confirmServerRunning` (409 `worldplayers.server_running` altrimenti), con la stessa regola per un giocatore non connesso quando il server e' su
  (avviso best-effort). Con il canale spento restano le regole di prima.

L'interfaccia, per un giocatore `playing` e con il canale scrivibile, propone la modifica **live** al posto di quella su file.
