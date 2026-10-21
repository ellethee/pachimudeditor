# Contratto backend: giocatori dei MUD su file (`/api/world/players`)

Introdotto con l'**SDK 1.3** (lettura: elenco L1 e dettaglio completo con inventario/equipaggiamento L2) ed esteso con l'**SDK 1.4**
(scrittura L3: campi del giocatore e oggetti dell'inventario). Riguarda i giocatori salvati nei file di un MUD. Non sostituisce `/api/players` ([giocatori del DB pachimud](contract-players.md)), che resta com'e'.

Stesse convenzioni di [contratto API](contract.md): auth Bearer, envelope `{success,message,data}`, camelCase, errori
`detail[{loc,msg,type,code,params}]`. Il mondo si sceglie con `X-World` (o `?world=`) come le altre rotte.

## Capability

Additive e retrocompatibili (default `false`; i mondi e gli adapter esistenti non cambiano):

| capability | significato |
| --- | --- |
| `supportsPlayerRecords` | le rotte `info`, `status`, elenco e dettaglio |
| `supportsPlayerInventory` | in piu', `GET /{id}/inventory` (richiede `supportsPlayerRecords`) |
| `supportsPlayerWrite` | (1.4) `PATCH /{id}`: modifica dei campi e delle tabelle |
| `supportsPlayerInventoryWrite` | (1.4) `POST/PATCH/DELETE /{id}/inventory/items...` (richiede `supportsPlayerInventory`) |

Senza la capability ogni rotta risponde 409 `world.capability_missing` (`params.capability`). Il mondo pachimud non la
dichiara. `supportsPlayers` (le rotte `/api/players`) e' un'altra cosa e non cambia.

## Rotte

- `GET /world/players/info` -> `PlayersInfo`: descrittore dichiarativo (struttura nel dettaglio più avanti in questa pagina).
- `GET /world/players/status` -> `{serverRunning: bool|null, detection}`: `true` solo se si e' trovato il server di gioco,
  `null` = non rilevabile (mai `false`: l'assenza di prove non e' una prova). Non blocca mai nulla.
- `GET /world/players` paginata (`page`+`pageSize`), `search` sul nome, `orderBy` tra `id, name, level, classLabel, raceLabel, gold, roomVnum, lastLoginAt, playedSeconds` (default: ordine dell'adapter, per nome) -> `PlayerSummary[]`
- `GET /world/players/{id}` -> `PlayerDetail`; 404 `worldplayers.not_found` se l'id non esiste o non e' valido.
- `GET /world/players/{id}/inventory` -> `PlayerInventory`.

L'`id` e' **opaco** per il client (Diku: il nome del file senza estensione). Gli id con separatori di percorso, `..` o
caratteri di controllo sono 404 gia' nel core; l'adapter li valida di nuovo con la propria regola (mai 500, mai path traversal).

### Scrittura (SDK 1.4)

- `PATCH /world/players/{id}` body `PlayerPatch` = `{revision?, confirmServerRunning?, details?: {nome: valore}, lists?: {nome: [righe]}}` -> `PlayerDetail` riletto.
  Solo i campi presenti cambiano; `details` ha come chiavi i `detailFields` con `readOnly: false`; `lists` **sostituisce** l'intera tabella.
  La **password non e' mai modificabile** (ne' un campo ne' un nome ammesso: `password`/`pwd` danno 422 `read_only`), come il nome (identita' del file) e il livello (derivato da `levels`).
- `POST /world/players/{id}/inventory/items` body `PlayerItemAdd` = `{vnum, wearSlot?, containerId?, revision?, confirmServerRunning?}` -> 201 `PlayerInventory`.
  L'oggetto e' creato dal **prototipo del mondo** (vnum inesistente: 404 `worldplayers.unknown_object`); `wearSlot` e' uno di `PlayersInfo.wearSlots`
  (omesso/null = portato); `containerId` e' il `PlayerItem.id` di un contenitore (incompatibile con `wearSlot`).
- `PATCH /world/players/{id}/inventory/items/{itemId}` body `PlayerItemUpdate` = `{wearSlot (obbligatorio, null = portato), revision?, confirmServerRunning?}` -> `PlayerInventory`.
- `DELETE /world/players/{id}/inventory/items/{itemId}?revision=&confirmServerRunning=` -> `PlayerInventory`: toglie l'oggetto **con il suo contenuto**.

Ogni scrittura, in quest'ordine: mondo non `read_only` (409 `world.read_only`) -> capability (409 `world.capability_missing`) -> id valido (404) ->
**server acceso**: se `GET /status` dice `serverRunning: true` serve `confirmServerRunning: true`, altrimenti 409 `worldplayers.server_running` (non rilevabile o
spento: si scrive normalmente) -> adapter: `revision` (409 `worldplayers.conflict` se il file e' cambiato dopo la lettura; assente = nessun controllo),
validazione, **copia `<file>.bak`** del contenuto precedente (una sola generazione, stessi permessi) e scrittura atomica.

`revision` (in `PlayerDetail` e `PlayerInventory`) e' un'impronta del contenuto del file letto (per Diku: SHA-256 troncato; per il file giocatore **senza** i byte della
password), non l'mtime: non cambia se il file non cambia e non rivela nulla. L'inventario ha una revisione propria (il file rent); dopo una scrittura
la risposta porta la nuova.

Un'operazione che non cambia nulla (stessi valori) non scrive ne' crea `.bak`.

## DTO

- `PlayerSummary` = `{id, name, level, classLabel, raceLabel, sex, gold, roomVnum, lastLoginAt, playedSeconds, hasPassword, online, problem, extra}`.
  Tutti i campi tranne `id` e `name` sono `null` se il MUD non li ha. `hasPassword` e' solo un booleano: **mai** la password,
  l'hash o loro prefissi/lunghezze. `online` e' `true` solo se il MUD lo sa con certezza (su file: `null`). `problem` e' un codice stabile
  se il file e' illeggibile (`bad_size`, `outside_dir`, `not_regular`, `unreadable`): la riga resta visibile senza dati. `extra` porta i
  campi specifici del MUD (le colonne `source: "extra"` di `PlayersInfo`).
- `PlayerSummary.revision` (1.4) e `PlayerInventory.revision`: impronta da rimandare nelle scritture.
- `PlayerDetail` = summary + `details` (mappa nome -> valore, un valore per ogni `detailFields`) + `lists` (nome -> righe, una tabella per ogni `detailLists`).
- `PlayerInventory` = `{items, problem, extra}` con `problem` in `truncated_header, too_many_items, truncated, trailing_data, owner_mismatch` (gli oggetti leggibili ci sono comunque); `extra` = dati del file (per Diku: `rentFile, goldLeft, totalCost, lastUpdate, minimumStay, declaredNumber`).
- `PlayerItem` = `{id, vnum, name, keywords, wearSlot, depth, known, extra}`: `wearSlot` nullo = portato; `depth` > 0 = dentro un contenitore; `known` = il prototipo esiste nel mondo.

## `PlayersInfo` (dichiarativo)

```json
{
  "columns":      [{"name": "level", "labelKey": "playerFiles.col.level", "type": "number", "sortable": true, "source": "field"}],
  "detailFields": [{"name": "str", "labelKey": "...", "type": "number", "group": "abilities", "readOnly": true, "enum": null, "nullable": true}],
  "detailLists":  [{"name": "skills", "labelKey": "...", "columns": [{"name": "learned", "labelKey": "...", "type": "number"}]}],
  "hasAccounts": false,
  "onlinePolicy": "warn"
}
```

- `columns[].type`: `text|number|datetime|boolean|duration` (secondi); `source: "extra"` legge `extra[name]`.
- `detailFields` riusa `ExtraFieldDescriptor` (`type` text/number/boolean/flags/enum/select/json; `group` = sezione del dettaglio, `flags` usa la lista `enum` di `GET /api/meta/enums`).
- `wearSlots` (1.4): gli slot ammessi per `PlayerItem.wearSlot` / `PlayerItemAdd.wearSlot`, nell'ordine del MUD.
- `onlinePolicy: "warn"`: il frontend mostra l'avviso «il server potrebbe essere in esecuzione». Letture sempre permesse.
- `hasAccounts` e' `false` per i MUD su file (l'account non esiste nei file).

## Codici errore aggiunti

| code | status | params |
| --- | --- | --- |
| `worldplayers.not_found` | 404 | |
| `worldplayers.server_running` (1.4) | 409 | |
| `worldplayers.conflict` (1.4) | 409 | |
| `worldplayers.invalid_value` (1.4) | 422 | `field`, `reason` (`type`, `range`, `too_long`, `charset`, `read_only`, `unknown_field`, `unknown_flag`, `unknown_class`, `duplicate`, `too_many`, `enum`), `min`/`max` |
| `worldplayers.file_unwritable` (1.4) | 409 | `problem` (`bad_size`, `outside_dir`, `not_regular`, `unreadable`, `truncated_header`, `too_many_items`, `truncated`, `trailing_data`, `owner_mismatch`) |
| `worldplayers.unknown_object` (1.4) | 404 | `vnum` |
| `worldplayers.item_not_found` (1.4) | 404 | |
| `worldplayers.item_invalid` (1.4) | 409 | `reason` (`slot_taken`, `slot_in_container`, `inventory_full`, `too_deep`, `container_invalid`), `max` |
| `world.capability_missing` (esistente) | 409 | `capability` |

## Scrivere un adapter

Vedi [SDK e adapter esterni](../adapters/sdk.md#giocatori-su-file-sdk-13-scrittura-14): mixin `PlayersAdapter`, capability, test di guardia.
Adapter oggi: `dikumod` ([formato e mappatura](../adapters/dikumod.md#giocatori)). Il contratto e' pensato per
accogliere anche basedmud (file testuali `player/<Nome>`) e `mapping` senza cambiare le rotte.
