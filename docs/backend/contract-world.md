# Contratto backend — app `world` (sola lettura)

Base: `/api/world`. Stesse convenzioni di [contratto API](contract.md) (auth Bearer, envelope `{success, message, data}`,
camelCase, errori `{detail: [{loc, msg, type, code?, params?}]}`).

## `GET /world/overview`
`data = { counts, zones, warnings, warningTotals }`
- `counts`: `zones, zonesEnabled, zonesDisabled, rooms, mobs, objects, mobInstances, objectInstances, accounts, characters`.
- `zones[]` (ordine per vnum): `id, vnum, name, enabled, bottomVnum, topVnum, rooms, mobs, objects, rangeUsagePct, resetCommands`.
  `rangeUsagePct` = vnum distinti (stanze+mob+oggetti della zona) dentro `[bottomVnum, topVnum]` / ampiezza del range, 1 decimale;
  `null` se il range e' 0-0 ("da assegnare").
- `warnings[]`: `kind, entityType (zone|room|mob|object), entityId, vnum, name, zoneId, zoneName, params`. Al massimo 100 per `kind`;
  i totali reali in `warningTotals` (`{kind: n}`, solo i `kind` presenti). `kind`:
  - `room_empty_description` (stanza con descrizione vuota/solo spazi)
  - `exit_without_target` (entita' = la stanza; `params.direction` = intero Direction)
  - `zone_empty_reset_script` (zona senza comandi di reset ma con almeno un mob o oggetto)
  - `vnum_out_of_range` (stanza/mob/oggetto con vnum fuori dal range della sua zona; `params.bottom|top`; zone 0-0 escluse)
  - `mob_never_loaded` (nessun `LOAD_MOB` lo carica), `object_never_loaded` (nessun LOAD/GIVE/EQUIP/PUT lo usa, ne' come contenitore)

## `GET /world/zone-graph`
`data = { nodes: [{id, vnum, name, enabled, rooms, isolated}], edges: [{fromZoneId, toZoneId, count}] }`.
Archi orientati: `count` uscite da stanze di `fromZoneId` verso stanze di `toZoneId` (solo se le zone differiscono).
`isolated` = nessun arco entrante ne' uscente.

## `GET /world/search?q=&types=&limit=`
- `q` obbligatorio (1-100 car., trim); `types` = lista separata da virgola di `zone,room,mob,object` (default tutti);
  `limit` per tipo (1-100, default 20).
- Match: prefisso del vnum OPPURE sottostringa case-insensitive su zone (name, builder), stanze (name), mob/oggetti
  (keywords, shortDescription). `%`, `_` e `\` sono caratteri letterali.
- `data = { q, zones, rooms, mobs, objects }`, ciascuno `{ items: [{id, vnum, name, keywords, zoneId, zoneName}], total }`
  (`items` ordinati per vnum e limitati, `total` = corrispondenze reali; tipo non richiesto = vuoto). `keywords` solo per mob/oggetti;
  per le zone `zoneId == id`.

## `GET /world/next-zone-range?span=100`
`span` 1-100000 (default 100). `data = { bottomVnum, topVnum }`: primo range di `span` vnum consecutivi (da 1 in su, buchi inclusi) che non
tocca il range di nessuna zona (0-0 ignorati; non guarda i vnum di contenuto fuori range). `topVnum = bottomVnum + span - 1`.

## Codici errore

| code | status | params |
| --- | --- | --- |
| `world.invalid_types` (valore ignoto in `types`) | 422 | `types` |
| `world.empty_query` (`q` fatto solo di spazi) | 422 | — |
