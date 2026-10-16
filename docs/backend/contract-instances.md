# Contratto backend — istanze vive (`/api/instances`)

App `instances`. Valgono le convenzioni di [contratto API](contract.md) (auth Bearer, envelope `{success,message,data}`,
camelCase, liste `{items,total,page,pageSize,pages}` paginate solo con `page`+`pageSize`, errori `detail[{loc,msg,type,code,params}]`).
Il game server tiene le istanze in memoria: modificarle a server fermo. Le istanze sono `MobInstance` / `ObjectInstance`.

## Mob vivi — `/instances/mobs`
- `GET /instances/mobs` paginata -> `MobInstanceOut[]`. Query: `search` (id istanza con o senza `#`, keywords/descrizione/vnum del
  prototipo, nome stanza), `roomId`, `zoneId` (zona della stanza), `prototypeId`, `prototypeVnum`; `orderBy`: `id, prototypeVnum,
  prototypeName, roomVnum, roomName, zoneName, hitPointsCurrent, hitPointsMax, gold` (altro: 422 `api.invalid_order_by`). Default: `-id`.
- `GET /instances/mobs/{id}` -> `MobInstanceDetail` (= `MobInstanceOut` + `items: ObjectInstanceOut[]`, oggetti portati/indossati).
- `POST /instances/mobs` `{prototypeId, roomId, hitPoints?, gold?}` -> 201 `MobInstanceDetail`. `hitPoints` assente: tirati dai dadi del prototipo
  (PF attuali = massimi).
- `PUT /instances/mobs/{id}` `{hitPointsCurrent?, hitPointsMax?, gold?, roomId?}` (solo i campi inviati; PF e stanza non azzerabili, `gold: null` azzera) -> `MobInstanceDetail`.
- `DELETE /instances/mobs/{id}?contents=destroy|drop` -> 204. `destroy` (default) elimina anche cio' che il mob porta (e il contenuto dei
  suoi contenitori); `drop` lascia gli oggetti nella stanza del mob, senza slot.

`MobInstanceOut`: `id, prototypeId, prototypeVnum, prototypeName, prototypeZoneId, shopId, roomId, roomVnum, roomName, zoneId, zoneName,
hitPointsCurrent, hitPointsMax, gold (|null), itemCount`.

## Oggetti vivi — `/instances/objects`
- `GET /instances/objects` paginata -> `ObjectInstanceOut[]`. Query: `search` (id istanza, keywords/descrizione/vnum del prototipo), `roomId` /
  `zoneId` (stanza *effettiva*: dove giace, o dove sta il contenitore/mob/personaggio che lo porta), `prototypeId`, `prototypeVnum`,
  `objectType` (intero, del prototipo), `kind` (`room|container|mob|character`, 422 `instances.invalid_location_kind` se altro) con `holderId`
  opzionale (id esatto del possessore); `orderBy`: `id, prototypeVnum, prototypeName, objectType, roomVnum, zoneName, charges, liquidAmount`. Default: `-id`.
- `GET /instances/objects/{id}` -> `ObjectInstanceDetail` (= `ObjectInstanceOut` + `contents: ObjectInstanceOut[]`).
- `POST /instances/objects` `{prototypeId, location: {kind, targetId, equippedSlot?}, charges?, liquidAmount?}` -> 201 `ObjectInstanceDetail`.
- `PUT /instances/objects/{id}` `{charges?, liquidAmount?, liquidType?, liquidPoisoned?, location?}` (solo i campi inviati; `null` su un valore
  numerico lo riporta a quello del prototipo; `location: null` e' rifiutato) -> `ObjectInstanceDetail`. Spostare un contenitore non sposta il suo contenuto.
- `DELETE /instances/objects/{id}?contents=destroy|drop` -> 204. Per un contenitore: `destroy` (default) ne elimina il contenuto, `drop` lo lascia
  dove stava il contenitore (stessa stanza o stesso inventario, senza slot).

`ObjectInstanceOut`: `id, prototypeId, prototypeVnum, prototypeName, prototypeZoneId, objectType (int), wearSlots (wearFlags senza "take"),
locationKind, locationId, locationLabel, equippedSlot, roomId, roomVnum, roomName, zoneId, zoneName (stanza effettiva, nulli se non ne ha),
charges, liquidAmount, liquidType, liquidPoisoned, contentCount`.

Regole di posizione: esattamente uno tra stanza / contenitore / mob / personaggio. `equippedSlot` solo con `mob`/`character`, deve essere un
`wearFlags` del prototipo (non `take`) e libero. Il contenitore deve essere un oggetto `CONTAINER` non a sua volta contenuto, il prototipo spostato non puo'
essere un contenitore, e non si supera la capacita' (`value0` del prototipo contenitore; `null` = illimitata; lo spostamento nello stesso
contenitore pieno e' ammesso). `charges` solo per bacchette/bastoni, campi liquido solo per contenitori di liquido. Valori numerici >= 0.

## Codici errore (tutti 422 salvo indicato)
| code | status | params |
| --- | --- | --- |
| `instances.mob_not_found` / `instances.object_not_found` | 404 | `id` |
| `instances.mob_prototype_not_found` / `instances.object_prototype_not_found` / `instances.room_not_found` / `instances.container_not_found` | 422 | `id` |
| `instances.holder_not_found` (mob/personaggio di destinazione) | 422 | `kind`, `id` |
| `instances.not_a_container` / `instances.container_nested` | 422 | `id` |
| `instances.container_full` | 422 | `id`, `capacity` |
| `instances.container_self` / `instances.container_in_container` / `instances.location_empty` / `instances.slot_not_allowed` | 422 | — |
| `instances.invalid_location_kind` | 422 | `kind` |
| `instances.slot_invalid` | 422 | `slot`, `allowed` |
| `instances.slot_taken` | 422 | `slot` |
| `instances.hp_min` / `instances.hp_exceeds_max` | 422 | — |
| `instances.negative_value` | 422 | `field` |
| `instances.charges_not_allowed` / `instances.liquid_not_allowed` | 422 | — |
| `instances.invalid_contents_policy` | 422 | `value` |
| `api.invalid_order_by` (pachifast) | 422 | `field` |
