# Contratto backend: giocatori (`/api/players`)

Stesse convenzioni di [contratto API](contract.md) (auth Bearer obbligatoria, envelope `{success,message,data}`, camelCase,
DELETE 204 senza body, paginazione solo con `page`+`pageSize`, errori `detail[{loc,msg,type,code,params}]`).
Gli ID nelle URL sono gli id di riga (non i vnum). L'hash della password non e' mai restituito.

## Account — `/players/accounts`
- `GET /players/accounts` paginata. `search`: username/email; filtro esatto `isBanned`; `orderBy`: id, username, email, createdAt, lastLoginAt, isBanned (default `username`) -> `AccountOut[]`
- `POST /players/accounts` `{username (3-32, senza spazi), password (8-128), email?}` -> 201 `AccountOut`. 409 `players.username_taken` / `players.email_taken`
- `GET /players/accounts/{id}` -> `AccountOut`; 404 `players.account_not_found`
- `PUT /players/accounts/{id}` `{email}` (`null` o stringa vuota = rimuovi; 409 `players.email_taken`)
- `POST /players/accounts/{id}/ban` | `/unban` (idempotenti) -> `AccountOut`
- `POST /players/accounts/{id}/password` `{password}` (hash Argon2id) -> `AccountOut`
- `DELETE /players/accounts/{id}?cascade=false` 204. Con personaggi e senza `cascade=true`: 409 `players.account_has_characters` (`count`). Con `cascade=true` elimina account, personaggi e relativi oggetti
- `AccountOut` = `{id, username, email, createdAt, lastLoginAt, isBanned, characterCount}`

## Personaggi — `/players/characters`
- `GET /players/lookups` -> `{sex, position: [{value,label}], races, classes: [{id,name}]}` (razze/classi riletti dagli YAML)
- `GET /players/characters` paginata. `search`: name/title/classId/raceId; filtri esatti `accountId`, `classId`, `raceId`, `currentRoomId`; `orderBy`: id, name, level, accountId, createdAt, lastPlayedAt, gold (default `name`) -> `CharacterSummary[]` (`id, accountId, accountUsername, name, level, classId, raceId, sex, gold, hitPointsCurrent/Max, currentRoomId, currentRoomVnum, currentRoomName, createdAt, lastPlayedAt`)
- `GET /players/characters/{id}` -> `CharacterDetail` (= summary + experience, mana, sei caratteristiche, strengthPercentile, practices, alignment, position, hunger/thirst/drunk, poisonTicks, wimpyLevel, isPlayerKiller, title, questPoints, bankGold, knownSkillIds, preferences, activeQuestIds, completedQuestIds, skillPercentages, questProgress, `itemCount`). 404 `players.character_not_found`
- `PUT /players/characters/{id}` patch parziale (`null` solo su `currentRoomId`). Validazioni: `accountId` -> 422 `players.invalid_account`; `currentRoomId` (id stanza) -> 422 `players.invalid_room`; `classId`/`raceId` contro le definizioni YAML -> 422 `players.invalid_class` / `players.invalid_race`; `name` univoco -> 409 `players.name_taken`. `skillPercentages`/`questProgress` non modificabili da qui
- `POST /players/characters/{id}/teleport` `{roomId}` -> `CharacterDetail` (422 `players.invalid_room`)
- `DELETE /players/characters/{id}?cascade=false` 204. Con oggetti posseduti e senza cascade: 409 `players.character_has_items` (`count`); `cascade=true` elimina anche l'inventario
- Non esiste la creazione di personaggi (si fa dal gioco).

## Inventario — `/players/characters/{id}/inventory`
Basato su `ObjectInstance.character_id` (oggetti portati/equipaggiati) piu' gli oggetti annidati in contenitori ricorsivamente (`container_instance_id`).
- `GET` -> `ItemOut[]` `{id, prototypeId, vnum, keywords, shortDescription, objectType, equippedSlot, containerInstanceId, wearFlags, liquidAmount, charges}`
- `POST` `{prototypeId | vnum, equippedSlot?}` -> 201 `ItemOut` (422 `players.prototype_required` / `players.invalid_prototype`)
- `PUT /{itemId}` `{equippedSlot: string|null}` -> `ItemOut` (404 `players.item_not_found`; 422 `players.item_in_container` se l'oggetto e' dentro un contenitore)
- `DELETE /{itemId}` 204: elimina l'istanza e il suo contenuto

## Codici errore aggiunti
| code | status | params |
| --- | --- | --- |
| `players.account_not_found` / `players.character_not_found` / `players.item_not_found` | 404 | `id` |
| `players.username_taken` | 409 | `username` |
| `players.email_taken` | 409 | `email` |
| `players.name_taken` | 409 | `name` |
| `players.account_has_characters` | 409 | `count` |
| `players.character_has_items` | 409 | `count` |
| `players.invalid_account` / `players.invalid_room` / `players.invalid_class` / `players.invalid_race` | 422 | `id` |
| `players.invalid_prototype` / `players.prototype_required` / `players.item_in_container` | 422 | |
