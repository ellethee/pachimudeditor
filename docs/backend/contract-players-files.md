# Contratto backend: giocatori dei MUD su file (`/api/world/players`)

Introdotto con l'**SDK 1.3**. Solo lettura: elenco (L1) e dettaglio completo con inventario/equipaggiamento (L2) dei giocatori
salvati nei file di un MUD. Non sostituisce `/api/players` ([giocatori del DB pachimud](contract-players.md)), che resta com'e'.

Stesse convenzioni di [contratto API](contract.md): auth Bearer, envelope `{success,message,data}`, camelCase, errori
`detail[{loc,msg,type,code,params}]`. Il mondo si sceglie con `X-World` (o `?world=`) come le altre rotte.

## Capability

Additive e retrocompatibili (default `false`; i mondi e gli adapter esistenti non cambiano):

| capability | significato |
| --- | --- |
| `supportsPlayerRecords` | le rotte `info`, `status`, elenco e dettaglio |
| `supportsPlayerInventory` | in piu', `GET /{id}/inventory` (richiede `supportsPlayerRecords`) |

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
Nessuna rotta di scrittura: POST/PUT/PATCH/DELETE su queste URL rispondono 404/405.

## DTO

- `PlayerSummary` = `{id, name, level, classLabel, raceLabel, sex, gold, roomVnum, lastLoginAt, playedSeconds, hasPassword, online, problem, extra}`.
  Tutti i campi tranne `id` e `name` sono `null` se il MUD non li ha. `hasPassword` e' solo un booleano: **mai** la password,
  l'hash o loro prefissi/lunghezze. `online` e' `true` solo se il MUD lo sa con certezza (su file: `null`). `problem` e' un codice stabile
  se il file e' illeggibile (`bad_size`, `outside_dir`, `not_regular`, `unreadable`): la riga resta visibile senza dati. `extra` porta i
  campi specifici del MUD (le colonne `source: "extra"` di `PlayersInfo`).
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
- `onlinePolicy: "warn"`: il frontend mostra l'avviso «il server potrebbe essere in esecuzione». Letture sempre permesse.
- `hasAccounts` e' `false` per i MUD su file (l'account non esiste nei file).

## Codici errore aggiunti

| code | status | params |
| --- | --- | --- |
| `worldplayers.not_found` | 404 | |
| `world.capability_missing` (esistente) | 409 | `capability` |

## Scrivere un adapter

Vedi [SDK e adapter esterni](../adapters/sdk.md#giocatori-su-file-sdk-13): mixin `PlayersAdapter`, capability, test di guardia.
Adapter oggi: `dikumod` ([formato e mappatura](../adapters/dikumod.md#giocatori-in-sola-lettura)). Il contratto e' pensato per
accogliere anche basedmud (file testuali `player/<Nome>`) e `mapping` senza cambiare le rotte.
