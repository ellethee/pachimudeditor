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

La capability `supportsLive` (e `supportsLiveInventory`) e' dichiarata da dikumod solo se `params.live` e' configurato e non `enabled: false`.

## Rotte

| Rotta | Esito |
| --- | --- |
| `GET /world/live/status` | `LiveStatus`: **sempre 200**, un MUD spento e' `state: unreachable`. Mai socket o token |
| `GET /world/live/who` | `LiveWho` `{players[], count, truncated}` (anche link morti: `state` `playing`/`linkdead`/`polymorph`) |
| `GET /world/live/info` | `LiveServerInfo` (uptime, giocatori, contatori del mondo) |
| `GET /world/live/zones` | `{zones[{index,num,name,bottom?,top,lifespan,age,resetMode,started}]}`: le zone **come le vede il gioco** |
| `GET /world/live/players/{name}` | `{name,state,fields,editableFields}`: valori correnti **in memoria** |
| `PATCH /world/live/players/{name}` | body `{fields, save?=true, confirmImmortal?=false}` -> `{name,applied{campo:{old,new}},saved,warnings[]}` |
| `POST /world/live/zones/reset` | body `{zone}` oppure `{room}` (uno solo), `onlyIfEmpty?` -> `{zone,name,executed}` |
| `POST /world/live/zones/reload` | body `{vnum}` -> `{zone,name,reloaded,rooms,mobs,objects}`: il gioco rilegge dai file la zona e rifa' il reset. Estensione **pachimud** (comando `zone.reload`; altrove 409 `worldlive.command_disabled`); mai ritentata. Se il gioco non riesce a rileggere i file: 409 `worldlive.reload_failed` (`zone` nel messaggio), la zona resta com'era |
| `GET /world/live/content/validate?strict=` | `{ok,errors,warnings,issues[{severity,code,message,file,line}]}`: il gioco controlla **tutti** i file dei contenuti come li carica (come `pachimud validate --json`; `file`/`line` sono `null` se il problema non sta in un file; con `strict` anche gli avvisi fanno `ok=false`). Estensione **pachimud** (`content.validate`, lettura; altrove 409 `worldlive.command_disabled`) |
| `POST /world/live/content/reload` | body `{kind}` con `kind` in `races|classes|skills|tables|socials|locales|all` -> `{ok,kind,reloaded{categoria:[id]},errors[]}`: il gioco rilegge dai file e sostituisce i registri in memoria, **tutto o niente**. Estensione **pachimud** (`content.reload`, scrittura, serve `allow_write`); mai ritentata. Se un file non si legge: 409 `worldlive.content_reload_failed` con `detail[0].params.issues[]` (`severity`,`code`,`message`,`file`,`line`) e il gioco resta com'era; `kind` sconosciuto 422. Non tocca giocatori connessi, zone/stanze/mob ne' hook Python; gli errori *semantici* (id inesistenti, segnaposto) non bloccano la ricarica, li riporta `content/validate` |
| `DELETE /world/live/boards/{boardId}/messages/{messageId}` | `messageId` = id riga di `board_message`, non la posizione -> `{ok,boardId,id,remaining}`: il gioco toglie il messaggio dal DB e dalla sua copia in memoria (estensione pachimud, comando `board.delete`, scrittura). Messaggio o bacheca inesistenti (o id di un'altra bacheca) 404 `worldlive.not_found`; mondo `read_only` 409 `world.read_only`; senza `allow_write` 409 `worldlive.command_disabled`. Mai ritentato |
| `DELETE /world/live/boards/{boardId}` | -> `{ok,boardId,removed}`: svuota la bacheca nel DB e nella memoria del gioco (comando `board.clear`, scrittura). Mai ritentato |
| `GET /world/live/instances?roomVnum=\|mobVnum=\|objVnum=\|zoneVnum=&limit=` | `{instances[{instanceId,kind,vnum,roomVnum}],count,truncated}`: istanze in memoria, **una sola** chiave (422 `worldlive.bad_params` altrimenti). Estensione **pachimud** (`instances.list`) |
| `POST /world/live/load/mob`, `/load/obj` | body `{vnum, room}` oppure `{vnum, player}`, `count?` 1..10, `notify?` -> `{loaded[]}` |
| `POST /world/live/echo` | body `{text}` + **una** tra `all: true`, `player`, `room` -> `{recipients}` |
| `GET /world/live/players/{name}/inventory` | inventario live: `{name,carryWeight,carryItems,count,truncated,items[]}`, elenco piatto in preordine (vedi [inventario](#inventario-e-oggetti-istanza)) |
| `GET /world/live/players/{name}/inventory/item?ref=` | un oggetto (`LiveItem`) con anche `wearFlags`, `cost`, `costPerDay`, `bitvector`; 404 `worldlive.not_found` se il `ref` non risolve |
| `PATCH /world/live/players/{name}/inventory/item?ref=` | body `{expect:{vnum,fp}, set:{...}, save?=true}` -> `{name,fp,saved,warnings[],item}` |
| `DELETE /world/live/players/{name}/inventory/item?ref=&fp=&vnum=&save=` | toglie e **distrugge** l'oggetto -> `{name,removed,destroyed,saved,warnings[]}` |

`fields` ha i nomi del protocollo: `gold`, `bankGold`, `exp`, `hit`, `mana`, `move`, `str`, `strAdd`, `int`, `wis`, `dex`, `con`, `chr`, `alignment`, `spellsToLearn`
e gli oggetti annidati `levels: {classe: livello}` e `conditions: {drunk|full|thirst: valore}`. Quelli accettati davvero dal MUD sono in `status.editableFields`
(un campo non dichiarato e' 422 `worldlive.bad_params`). Il nome di un giocatore deve essere `[A-Za-z][A-Za-z0-9_-]{0,19}` (altrimenti 404 senza interrogare il MUD).

**Immortali.** Promuovere una classe a un livello >= 51 (e maggiore dell'attuale) senza `confirmImmortal: true` e' rifiutato con 409
`worldlive.immortal_confirmation_required` e **nulla** viene modificato (neppure gli altri campi della richiesta); con la conferma la risposta ha
`warnings: ["immortal_level"]`. L'interfaccia mostra l'avvertenza («stai creando un immortale: avra' i poteri di un dio nel gioco») e invia il flag solo dopo la conferma.

## Inventario e oggetti istanza

Capability `supportsLiveInventory` (dichiarata con `supportsLive`; richiede `supports_live`, altrimenti 409 `world.capability_missing` con `params.capability = supports_live_inventory`). Il MUD
deve inoltre dichiarare la feature `inventory` in `hello`: si legge da `GET /status` (`features` contiene `inventory`); senza, le rotte rispondono 409 `worldlive.command_disabled`.
Stesse regole delle altre rotte: solo superuser, `X-World`, le scritture (`PATCH`, `DELETE`) anche su mondo non `read_only` (409 `world.read_only`), nessun ritentativo.

- **`ref`** e' una stringa **opaca** (`eq:5`, `inv:2`, `inv:2/0`): contiene `:` e `/`, quindi va **sempre in query** (`?ref=inv%3A2%2F0`), mai nel percorso. Cambia quando l'inventario cambia: va preso
  dall'ultima lettura **della stessa riga**. Un `ref` non valido (grammatica) e' 422 `worldlive.bad_params`; uno che non risolve e' 404 `worldlive.not_found` in lettura.
- **`expect`** `{vnum, fp}` (valori dell'ultima lettura; `vnum` puo' essere `null`) e' **obbligatorio** nelle scritture: nel corpo del `PATCH` (assente = 422), in query del `DELETE`
  (`fp` obbligatorio = 422; `vnum` assente vale `null`). Se `ref`/`expect` non coincidono col gioco: **409 `worldlive.stale_ref`** e nulla cambia. Su `stale_ref` il client rilegge l'elenco e lo chiede
  di nuovo all'utente: mai un nuovo invio automatico con un `ref` ricalcolato.
- **`set`** e' una patch parziale (almeno un campo): `name`, `shortDescription`, `description` (testi: 1..127/127/255 caratteri latin-1, niente `$`, `~` ne' controlli), `values` (1-4 elementi, `null` =
  invariato), `weight` (0..32767), `extraFlags` (0..2147483647), `timer` (0..1000000 o -7000000 = nessun timer), `affects` (1-5 elementi, `null` = invariato, `{location 0..64, modifier -32768..32767}`).
  Un campo non valido annulla l'intera richiesta: 422 `worldlive.value_out_of_range` (`field`, `min`, `max`), `worldlive.value_too_long` (testo oltre il limite: `field`, `max`), `worldlive.unencodable_text`,
  `worldlive.bad_params` (`field`: ad esempio `$` o `~` nel testo).
- `POST /load/obj` a un giocatore: la risposta ha `warnings: ["vnum_not_saveable"]` se il vnum e' > 32767 (il rent lo salva a 16 bit e al salvataggio l'oggetto si corrompe): l'interfaccia lo mostra sempre.
- Un oggetto **a terra** (creato in una stanza) non ha un `ref`: il protocollo indirizza solo equipaggiamento e inventario di un giocatore. Per modificare un oggetto appena creato lo si crea nell'inventario di un giocatore.
- Giocatore non connesso: 404 `worldlive.not_found`; connesso ma non in gioco (link morto, menu): 409 `worldlive.player_not_playing`.

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
| 409 | `worldlive.stale_ref` | l'oggetto non e' piu' quello letto (`ref`/`expect` non coincidono) |
| 409 | `worldlive.command_disabled` | comando non dichiarato da `hello` (classe `write` spenta nel MUD) |
| 422 | `worldlive.value_out_of_range` | valore fuori intervallo (`field`, `min`, `max`) |
| 422 | `worldlive.value_too_long` | testo di un oggetto oltre il limite del rent (`field`, `max`) |
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
