# Contratto backend webeditor (pachifast)

Base: `/api`. Docs interattive: `/docs`, schema completo `/api/v1/openapi.json`.

## Convenzioni generali

- **Auth**: tutte le route richiedono `Authorization: Bearer <access_token>` (login `POST /api/auth/token`,
  form-urlencoded `username`,`password`; refresh `POST /api/auth/refresh-token`). Senza token: 401.
- **Envelope**: ogni 2xx JSON e' `{ "success": true, "message": null, "data": <payload> }`. Le DELETE
  rispondono `204` senza body (niente envelope).
- **camelCase** in richieste e risposte (accettato anche snake_case in input).
- **Liste paginate** (`GET /zones|/rooms|/mobs|/objects`): `data = { items, total, page, pageSize, pages }`.
  Query: `page` (da 1), `pageSize`, `orderBy` (campi separati da virgola, prefisso `-` = decrescente,
  camelCase o snake_case), `search`, filtri esatti dove indicato. **Si pagina solo se sono presenti
  entrambi `page` e `pageSize`**, altrimenti tornano tutte le righe (il vecchio default era 25 per pagina).
  `orderBy` su campo non ammesso: 422 `api.invalid_order_by` (`loc: ["query","orderBy"]`). Ordine di
  default: `vnum`.
- **Errori**: status non-2xx con `{ "detail": [ { loc, msg, type, code?, params? } ] }`. Il frontend
  ragiona su `code` (+ `params`) e usa `msg` (gia' tradotto, `it` di default, oppure `Accept-Language`)
  come fallback. Gli errori di validazione 422 di FastAPI/Pydantic non hanno `code`.
  Per esportare i cataloghi a vue-i18n: `uv run pachifast locale export --dest-path <dir> --namespace errors.codes`.
- Enum (sectorType, direction, ...) sono **interi** sul filo; le opzioni per le select sono in `GET /meta/enums`.

### Codici errore (stabili)

| code | status | params |
| --- | --- | --- |
| `zones.not_found` / `rooms.not_found` / `rooms.exit_not_found` / `rooms.extra_not_found` / `mobs.not_found` / `objects.not_found` | 404 | `id` |
| `zones.vnum_taken` / `rooms.vnum_taken` / `mobs.vnum_taken` / `objects.vnum_taken` | 409 | `vnum` |
| `zones.not_empty` (zona con contenuto) | 409 | `rooms`, `mobs`, `objects` |
| `rooms.in_reset_usage` / `mobs.in_reset_usage` / `objects.in_reset_usage` (delete di un elemento usato da un comando di reset) | 409 | `count`, `zones` |
| `objects.in_exit_key_usage` (delete di un oggetto che e' `keyVnum` di un'uscita) | 409 | `count`, `zones` |
| `rooms.vnum_in_use` / `mobs.vnum_in_use` / `objects.vnum_in_use` (cambio di `vnum` di un elemento usato da reset o, per gli oggetti, da chiavi di uscita; a vnum invariato nessun controllo) | 409 | `count`, `zones` |
| `mobs.has_instances` / `objects.has_instances` (delete con istanze vive) | 409 | `count` |
| `rooms.has_instances` (delete con mob/oggetti dentro o personaggi la cui ultima stanza e' questa) | 409 | `mobs`, `objects`, `players` |
| `zones.range_overlap` (clone con `bottomVnum`/`topVnum` che si sovrappongono a un'altra zona) | 409 | `zone`, `zone_vnum` |
| `zones.invalid_vnum_range` / `zones.invalid_level_range` (PUT zona: valori finali incoerenti) | 422 | `bottom`,`top` / `min`,`max` |
| `zones.reset_unknown_mob` / `zones.reset_unknown_object` / `zones.reset_unknown_room` (PUT script: vnum inesistente; `loc` = `["body","commands",index]`) | 422 | `index`, `vnum` |
| `rooms.exit_door_state_invalid` (doorFlag NONE ma chiusa/serrata) / `rooms.exit_locked_needs_key` / `rooms.exit_key_unknown` / `rooms.exit_self_loop` | 422 | `vnum` solo per `exit_key_unknown` |
| `rooms.exit_direction_taken` | 409 | `direction` |
| `rooms.exit_not_in_room` / `rooms.extra_not_in_room` | 409 | |
| `common.editor.in_use` / `invalid_reference` / `duplicate` / `constraint_violation` (vincoli DB) | 409 | |
| `api.invalid_order_by` | 422 | `field` |

## Meta — `/meta`
- `GET /meta/enums` -> `{ sectorType, direction, doorFlag, zoneResetMode, sex, objectType, zoneCommandType: [{value,label}] }`
- `GET /meta/races`, `GET /meta/classes` -> `[{id, name}]` (rilette dagli YAML a ogni chiamata)
- (il vecchio `/ping` e' sostituito da `GET /api/health/`; i vecchi `/enums`, `/races`, `/classes` ora sono sotto `/meta`)

## Zone — `/zones`
- `GET /zones` paginata (`search`: name/builder/vnum; `orderBy`: id, vnum, name, builder, lifespanMinutes, resetMode, enabled) -> `ZoneOut[]`
- `POST /zones` (`ZoneIn`: vnum, name, builder, bottomVnum, topVnum, minLevel, maxLevel, lifespanMinutes, resetMode, enabled) -> 201 `ZoneOut`
- `GET /zones/next-vnum?span=99` -> `{vnum, bottomVnum, topVnum}`
- `GET|PUT|DELETE /zones/{id}` (PUT = patch parziale `ZonePatch`: valuta bottom<=top e min<=max sui valori finali -> 422; DELETE 204, 409 se non vuota)
- `GET /zones/{id}/summary` -> `{roomCount, mobCount, objectCount}`
- `GET /zones/{id}/next-vnum?kind=room|mob|object` -> `int`
- `POST /zones/{id}/clone` (`{vnum, name, copyResetCommands, bottomVnum?, topVnum?}`) -> 201 `ZoneOut`. Il range vnum non e' piu' copiato dalla sorgente: senza `bottomVnum`+`topVnum` (vanno dati insieme, 422 altrimenti) la copia nasce con range 0-0 ("da assegnare"); con un range che si sovrappone a un'altra zona 409 `zones.range_overlap`
- `GET|PUT /zones/{id}/reset-commands` -> `ResetCommandOut[]`; PUT body `{commands: [{commandType, ifFlag, arg1..arg4, argStr, ifValue?, comment?, extra?}]}` sostituisce tutto, `orderIndex` = posizione. `ifValue` (intero), `comment` ed `extra` esistono solo per i mondi che li supportano (Diku Modificato; pachimud li rifiuta con 422 `world.extra_unsupported`); `commandType` puo' essere un intero 7-10 (Diku Modificato: charm, odio, paura, zona del mob), vedi `docs/adapters/index.md`.
  Validazione PUT (422, tutto o niente): per tipo, `LOAD_MOB`/`LOAD_OBJECT` richiedono arg1 (vnum), arg2 (max), arg3 (stanza), arg4 (max per stanza) opzionale;
  `GIVE_OBJECT` arg1; `EQUIP_OBJECT` arg1 + `argStr` (slot, stringa libera); `PUT_OBJECT` arg1 + arg3 (vnum contenitore);
  `SET_DOOR_STATE` arg1 (stanza) + arg2 (direzione 0-5) + `argStr` OPEN|CLOSED|LOCKED (case-insensitive); `RANDOMIZE_EXITS` arg1.
  Nessun argomento negativo; `argStr` ammesso solo per EQUIP_OBJECT e SET_DOOR_STATE (errori Pydantic, senza `code`). I vnum di mob/oggetti/stanze devono esistere
  (422 `zones.reset_unknown_*` con `index` e `vnum`).
- `POST /zones/{id}/reset-commands/validate` body `{commands: [...]}` (stessa forma del PUT, ma senza vincoli per comando) -> `{ok, issues: [{index, severity: "error"|"warning", code, params, message}]}`; non salva.
  `ok` = nessun `error`. Errori: argomenti mancanti/negativi/non ammessi (`zones.reset_missing_arg|negative_arg|invalid_direction|slot_required|invalid_door_state|arg_str_not_allowed`), vnum inesistenti (`zones.reset_unknown_*`).
  Warning: `reset_if_flag_first`, `reset_no_mob_before` (G/E senza LOAD_MOB prima), `reset_container_not_loaded` (P senza LOAD_OBJECT/PUT del contenitore prima),
  `reset_max_zero`, `reset_max_high` (>100), `reset_room_cap_above_max` (arg4 > arg2), `reset_no_such_exit`, `reset_exit_without_door` (D su uscita assente / senza porta).

## Stanze — `/rooms`
- `GET /rooms` paginata (`search`: name/vnum; `zoneId` filtro esatto; `orderBy`: id, vnum, name, sectorType) -> `RoomOut[]`
- `POST /rooms` (`RoomIn`) -> 201 `RoomDetail`
- `GET /rooms/graph?zoneId=` (obbligatorio) -> `{nodes: [{id,vnum,name,sectorType,flags,x,y,danglingExits}], edges: [{id,fromRoomId,toRoomId,direction,doorFlag,twoWay,reverseExitId}]}`
- `GET|PUT|DELETE /rooms/{id}` -> `RoomDetail` (= `RoomOut` + `exits: ExitOut[]`, `extraDescriptions`); PUT con `vnum` cambiato: 409 `rooms.vnum_in_use` se usata da un reset; DELETE 204, 409 `rooms.in_reset_usage` se referenziata da un reset, 409 `rooms.has_instances` se ha istanze vive. **Le uscite di altre stanze che puntano alla stanza NON bloccano la delete**: restano con `targetRoomId` nullo
- `GET /rooms/{id}/usage` -> `ResetUsage[]` (`zoneId, zoneName, resetCommandId, orderIndex, commandType, source, exitId, roomId, roomVnum`; `source` = `"reset"` o, solo per gli oggetti, `"exit_key"`: in tal caso i campi del reset sono `null` e `exitId/roomId/roomVnum` sono valorizzati)
- `POST /rooms/{id}/clone` (`{vnum, name?}`) -> 201 `RoomDetail` (extra description copiate, uscite no)
- `POST /rooms/{id}/exits` (`ExitIn`) -> 201 `ExitOut`; `PUT|DELETE /rooms/{id}/exits/{exitId}`. Regole (422): `doorFlag` 0 (NONE) non ammette `isOpen: false` ne' `isLocked: true`; `isLocked` richiede `keyVnum`; `keyVnum` deve esistere come oggetto; `targetRoomId` non puo' essere la stanza stessa. Nel PUT sono valutate solo se il patch tocca i campi coinvolti (dati preesistenti incoerenti restano modificabili)
- `POST /rooms/{id}/extra-descriptions` (`{keywords,text}`) -> 201; `PUT|DELETE /rooms/{id}/extra-descriptions/{extraId}`

## Mob — `/mobs`
- `GET /mobs` paginata (`search`: shortDescription/keywords/vnum; `zoneId`; `orderBy`: id, vnum, level) -> `MobOut[]`
- `POST /mobs` -> 201; `GET|PUT|DELETE /mobs/{id}` (PUT con `vnum` cambiato: 409 `mobs.vnum_in_use` se in un reset; DELETE 204, 409 `mobs.in_reset_usage` / `mobs.has_instances`); `GET /mobs/{id}/usage` -> `ResetUsage[]`

## Oggetti — `/objects`
- `GET /objects` paginata (`search`: shortDescription/keywords/vnum; `zoneId`; `orderBy`: id, vnum, objectType) -> `ObjectOut[]`
- `POST /objects` -> 201; `GET|PUT|DELETE /objects/{id}` (PUT con `vnum` cambiato: 409 `objects.vnum_in_use` se in un reset o chiave di un'uscita; DELETE 204, 409 `objects.in_reset_usage` / `objects.in_exit_key_usage` / `objects.has_instances`); `GET /objects/{id}/usage` -> `ResetUsage[]` (include le uscite che lo usano come chiave)

## Validazione dei PUT parziali
- `null` esplicito su una colonna NOT NULL: 422 (prima 409 `common.editor.constraint_violation`). `null` ammesso solo su: mob `raceId/classId/debuffSkillId/shopId/teachesClassIds/teachesSkillIds`; oggetto `actionDescription/value0..3`; stanza `clanId/owner`; uscita `description/keywords/keyVnum/targetRoomId`.
- `>= 0`: `weight/cost/rent` (oggetti), `gold/experience` (mob), `healRate/manaRate` (stanze), `keyVnum`.

## Differenze rispetto al vecchio backend
- Auth obbligatoria (prima nessuna); CORS non piu' `*` ma elenco di origini localhost (il proxy dev non lo richiede).
- Envelope `{success,message,data}` su ogni 2xx; paginazione `{items,total,page,pageSize,pages}` (aggiunto `pages`);
  senza `page`+`pageSize` niente paginazione (prima default pageSize 25, max 1000); `pageSize=0` = tutto.
- `orderBy` non valido: 422 (prima ignorato); `orderBy` su campi fuori whitelist: 422.
- `search` e' ILIKE sulla stringa cosi' com'e' (prima trim + lower); stesse colonne.
- Errori: `detail` e' sempre una lista con `code` (prima stringa); messaggi it/en dal catalogo.
- `/ping` -> `/api/health/`; `/enums|/races|/classes` -> `/api/meta/...`.
- `GET /zones/{id}/next-vnum` ritorna `data: int` (nell'envelope). Resto dei payload invariato.

## Moduli aggiuntivi

Contratti dettagliati (endpoint, query, codici di errore) in file separati:

- [contratto world](contract-world.md) — panoramica del mondo, grafo tra zone, ricerca trasversale, prossimo range di zona.
- [contratto players](contract-players.md) — account, personaggi giocatore, inventario.
- [contratto instances](contract-instances.md) — istanze live di mob e oggetti.
- [contratto transfer](contract-transfer.md) — export/import di zona in YAML.
- [contratto content](contract-content.md) — razze e classi su YAML.


## Mondi (adapter)

`GET /api/worlds` elenca i mondi configurati con capability e descrizione dei campi; ogni richiesta puo' scegliere il mondo con l'header `X-World` o `?world=` (default: pachimud). Id ignoto: 404 `world.not_found`; area non supportata: 409 `world.capability_missing`; mondo in sola lettura: 409 `world.read_only`; aree specifiche di pachimud (`/api/world`, `/api/instances`, `/api/players`, `/api/transfer`, `/api/content`) su un mondo di altro tipo: 409 `world.not_pachimud`; database del mondo pachimud non utilizzabile: 503 `world.unavailable`; campo assente dallo schema del DB scritto con un valore non neutro: 422 `world.field_unsupported`. Le entita' zona/stanza/mob/oggetto hanno in piu' il campo `extra` (oggetto, vuoto per pachimud). Dettagli in `docs/adapters/index.md`.
