# Contratto backend: content (razze, classi, skill, tabelle, social, cataloghi)

Prefisso `/api/content`. CRUD sui file `definitions/races/*.yaml` e `definitions/classes/*.yaml`
(cartella da `PachimudConfig.definition_path`). Validazione con gli schemi `LoaderRace`/`LoaderClass` del gioco
piu' controlli extra (nomi di flag/taglia esistenti per le razze; caratteristiche valide e senza duplicati per le classi).
Scrittura con `ruamel.yaml` round-trip (commenti e formato preservati, si toccano solo le chiavi cambiate) e atomica
(file temporaneo + `os.replace`). **Il game server legge gli YAML solo all'avvio: le modifiche valgono dopo il riavvio.**

Id: `^[a-z0-9][a-z0-9_]{0,63}$` (= nome file senza estensione; immutabile). Nei body i campi sono camelCase
(`raceId`, `mobOnly`, `affectedBy`, `maxStats`, `classId`, `attrPrime`, `attrsPriority`, `thac000`/`thac032` = `thac0_00`/`thac0_32`, ...).
In `PUT` vengono applicati solo i campi **inviati**; `null` rimuove la chiave dal file.

## Endpoint (identici per `races` e `classes`)
- `GET /content/{kind}` -> `RaceItem[]`/`ClassItem[]` (anche disattivati e file non validi: `valid=false`, `error`), ordinati per nome.
- `POST /content/{kind}` (201) body = campi del file (`raceId`/`classId`, `name`, `description` obbligatori per le razze).
- `GET /content/{kind}/{id}`; `PUT /content/{kind}/{id}` (`raceId`/`classId` nel body deve coincidere col path).
- `POST /content/{kind}/{id}/disable|enable`: rinomina `<id>.yaml` <-> `<id>.yaml.disabled` (non piu' caricato dal game server). Nota: il flag `disabled:` delle classi oggi non e' copiato da `BaseClass.load_from_yaml`, quindi non e' usato.
- `DELETE /content/{kind}/{id}` -> 204 senza envelope. **409** `content.race_in_use` / `content.class_in_use` (`id`, `count`) se dei prototipi di mob usano la razza (`race_id`) / la classe (`class_id` o `teaches_class_ids`).
- Item: campi del file + `file`, `disabled`, `mobCount`, `valid`, `error`.
- `GET /content/options` -> `{mobFlags, offensiveFlags, resistanceFlags, formFlags, partFlags, affectedByFlags, sizes, stats}` (liste di nomi).
- `GET /content/status` -> `{races, classes, lastModified}` (epoch secondi, per il banner "riavvio necessario").

Errori: 404 `content.not_found`; 409 `content.id_taken`; 422 `content.invalid_id`, `content.id_mismatch`, `content.invalid` (param `detail`); 422 Pydantic senza code per tipi errati.

## Contenuti a strati: skill, social, tabelle, cataloghi, testi

Il gioco applica piu' **strati** di contenuti (`docs/contenuti.md` del gioco): il pacchetto (`params.base_definitions_path`, sola lettura per
l'editor), poi `definitions_path`. A parita' di id (o di nome file) vince lo strato dell'utente. Le rotte qui sotto **scrivono solo nello strato
dell'utente**: salvare un elemento che esiste solo nella base ne crea la copia (il layer diventa `user`, la base non si tocca); eliminare dallo
strato dell'utente ripristina quello di base (404 se l'elemento non e' dell'utente). Scrittura atomica, commenti salvi, UTF-8, massimo 512 KB per file.
Il controllo semantico completo e' del gioco (`content.validate`, vedi [canale live](contract-live.md)); l'editor controlla che il YAML si legga.
Con `read_only` ogni scrittura risponde 409 `world.read_only`.

- `GET /content/skills` -> `SkillItem[]` `{skillId, layer: user|base, kind, name, mana, levels{classe:livello}, error?}`; un file illeggibile ha solo `skillId`, `layer` ed `error`.
  Le traduzioni `skills/<id>.<lingua>.yaml` non sono skill.
- `GET /content/skills/{id}` -> come sopra con i campi semplici (`kind`, `name`, `description`, `disabled`, `mana`, `beats`, `fail`, `minPosition`, `violent`, `maxLearn`, `saving`, `element`, `targets[]`)
  e `advanced`: il YAML di **tutti gli altri campi** (`levels`, `effects`, `handler`, `objectHandler`, `affects`, `messages`, `extends`, ...).
- `POST /content/skills` (201) body `{skillId, ...campi semplici, advanced?}`; `PUT /content/skills/{id}` solo i campi inviati (`null` toglie la chiave; `advanced` sostituisce
  gli altri campi: le chiavi non piu' presenti sono tolte). 409 `content.id_taken`; 422 `content.invalid_id`, `content.invalid` (YAML con riga e colonna, o `advanced` che ripete un campo semplice).
- `DELETE /content/skills/{id}` -> 204.
- `GET /content/socials` -> `SocialItem[]` `{name, layer, aliases[], position, victimMinPosition, hide, messages{lingua:{chiave:testo}}}` (`tables/socials.yaml` e `socials.<lingua>.yaml`, strati e lingue fusi;
  chiavi dei testi `no_arg`, `others_no_arg`, `found`, `others_found`, `victim_found`, `not_found`, `auto`, `others_auto`).
  `POST /content/socials/{name}` (201) e `PUT /content/socials/{name}` scrivono **tutta** la voce (testi di tutte le lingue, testi vuoti omessi) in `tables/socials.yaml` dello strato dell'utente;
  `DELETE` la toglie. 409 `content.id_taken`.
- `GET /content/files/{area}` con `area` = `tables` (`tables/*.yaml`, **senza** i social), `locales` (`locales/<lingua>/**/*.yaml`) o `texts` (`texts/*.txt`) -> `[{path, layer, size}]`, strati fusi.
- `GET|PUT|DELETE /content/files/{area}/{path}`: `{path, layer, text}`; `PUT` body `{text}` crea o sostituisce nello strato dell'utente (un `.yaml` deve leggersi ed essere una mappa o una lista).
  Percorso: lettere, cifre, `_ - . /`, estensione dell'area, niente `..`: altrimenti 422 `content.invalid_path`; 422 `content.too_large` (`max` in KB); 422 `content.invalid` se il testo non e' UTF-8 valido.


## Negozi

Un negozio non e' un file: e' il campo `shop:` del mob (`extra.shop` di `/api/mobs`, chiavi del file: `produces[]`, `trades[]`, `profit_buy`, `profit_sell`, `room`, `open1`, `close1`,
`open2`, `close2`, `no_money_reaction`, `attacked_reaction`, `messages{chiave:{lingua:testo}}`, `handler`). Si modifica con `PUT /mobs/{id}` `{extra: {shop: {...}}}` (validato come `ShopProto`: 422
`pachimud.invalid_entry`; `null` toglie il negozio). Il vecchio `shopId` (`shop_id`) il gioco lo ignora.

- `GET /content/shops` -> `ShopItem[]` per i mob con `shop` o con `shop_id`, in ordine di vnum: `{vnum, name, zoneId, zoneName, hasShop, legacyShopId, produces[{vnum, name|null}], trades[], profitBuy,
  profitSell, room, roomName, open1, close1, open2, close2, handler}`. `name: null` = l'oggetto non esiste (il controllo del gioco lo segnala: `shop-object-missing`).
- `GET /content/boards` (capability `supports_boards`) -> `{boardTable, mailTable, boards[{boardId, count, objects[{vnum, name, zoneId, zoneName}], maxMessages|null, orphan}]}`: gli oggetti BOARD dei YAML (`board_id`, o il vnum come fa il gioco) piu' i `board_id` con messaggi nel DB (`orphan` = nessun oggetto); `boardTable`/`mailTable` falsi se la tabella opzionale manca (nessun errore).
- `GET /content/boards/{boardId}/messages?search=` -> `[{id, number, author, title, text, createdAt}]` dal piu' vecchio; `number` e' la posizione con cui li legge il gioco e non cambia con la ricerca (autore, titolo, testo). Bacheca senza messaggi: `[]`.
- `GET /content/mail` -> `{available, total, recipients[{recipient, count}]}`: solo conteggi per destinatario, il testo delle lettere non si legge mai.
- Nessuna rotta di scrittura su `/content`: il gioco tiene i messaggi in una copia in memoria e il numero e' la posizione nella lista, quindi cancellare dal DB la lascerebbe stantia. La moderazione passa dal canale live: `DELETE /api/world/live/boards/{boardId}/messages/{messageId}` e `DELETE /api/world/live/boards/{boardId}` (vedi `contract-live.md`).
- `GET /content/shops/options` -> `{objectTypes[], messageKeys[]}` (tipi comprabili e messaggi sostituibili).

## Locande

Una locanda e' il flag `receptionist` del mob (`extra.receptionist` di `/api/mobs`; con il mob nella stanza funzionano `offer` e `rent`).

- `GET /content/inns` -> `InnItem[]` per i mob con `receptionist`, in ordine di vnum: `{vnum, name, zoneId, zoneName, rooms[{vnum, name|null}]}`. `rooms` e' l'elenco delle stanze in cui un reset
  (di qualunque zona) carica il mob: vuoto = nessun reset lo carica; `name: null` = la stanza non esiste.

## Controllo dei contenuti (pachimud)

- `POST /content/checks/locate` con `{items: [{file, line}]}` (fino a 2000) -> `Located[]` nello stesso ordine: `{kind, vnum, zoneId}`. `kind`: `room|mob|object` (la voce che comincia alla riga piu'
  vicina prima di `line`, `vnum` valorizzato), `zone` (`zone.yaml`), `resets` (file dei reset), `file` (file di contenuto senza una voce precisa, riga assente) o `none` (file sconosciuto all'editor o `file`
  assente). Il percorso del gioco si confronta uguale e poi dal ramo `zones/<zona>/<file>`.
- `GET /content/checks/style` -> `{enabled, roomNameMax, descriptionMinLines, descriptionMaxLines, descriptionWidth, shortMax, longMax, timeWords[]}`: `validate.style` del `pachimud.yaml` del mondo
  (`config_path`) sui default del manuale (80, 3-8 righe da 80 colonne, 40, 80, parole `giorno notte pioggia neve`). Soglie illeggibili o non valide: default.

