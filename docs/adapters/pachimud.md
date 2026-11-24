# Adapter pachimud (`kind: pachimud`, contenuti su file YAML, giocatori nel database)

Dal commit `e958b4e` del gioco il database SQLite tiene **solo** `account` e `player_character` (piu' `alembic_version`).
Zone, stanze, uscite, mob, oggetti, reset, classi e razze sono file YAML sotto la `definition_path` del gioco. L'editor ha un
database SUO (utenti/opzioni, pachifast) separato da quello del MUD. `PachimudAdapter` NON importa il pacchetto `pachimud`:

- i **contenuti** (zone, stanze, mob, oggetti, reset) si leggono e si scrivono come file YAML (`store.py`), `id == vnum`;
- **giocatori e account** stanno nel DB di gioco, aperto con SQLAlchemy async (aiosqlite per SQLite) e riflesso
  (`MetaData.reflect`) invece di usare i modelli ORM del gioco;
- le istanze vive (mob/oggetti in gioco) esistono solo in RAM del gioco: **non c'e' piu' la capability `supports_instances`**
  (l'app `/api/instances` e la pagina «Istanze» sono state rimosse).

**Il gioco legge i YAML all'avvio**: le modifiche fatte dall'editor hanno effetto al riavvio, oppure subito con la ricarica a caldo del
canale live (`params.live`, vedi [pachimud-live](pachimud-live.md)): `zone.reload` per le zone e `content.reload` per razze, classi, skill, tabelle,
social e cataloghi. Il gioco non scrive mai i YAML, quindi non c'e' concorrenza di scrittura: l'editor rilegge un file se
cambia `(mtime, size)`, e quindi vede anche le modifiche manuali.

## Parametri del mondo

```yaml
webeditor_worlds:
  - id: pachimud
    kind: pachimud
    name: Pachimud
    params:
      definitions_path: ./definitions                 # OBBLIGATORIO (o config_path): zones/, classes/, races/
      database_url: sqlite+aiosqlite:///pachimud.db   # facoltativo: account e personaggi
      config_path: /percorso/pachimud.yaml            # facoltativo: il pachimud.yaml del game server
      live:                                           # facoltativo: canale live verso il gioco acceso
        socket: /percorso/assoluto/pachimud.sock
        token_env: LIVECTL_TOKEN                      # NOME della variabile (nel .env): mai il token nel yaml
        timeout_ms: 3000
```

- `definitions_path` (sinonimo `definition_path`, come nel `pachimud.yaml`): cartella `definitions/`. Contenuti = `zones/`,
  `classes/`, `races/`. Senza (e senza `config_path`) l'avvio fallisce con un errore chiaro.
- `database_url`: un URL senza driver async e' portato al driver async di default (`sqlite://` -> `sqlite+aiosqlite://`).
  I path SQLite relativi si risolvono rispetto alla cartella di lavoro (la cartella del `pachimudeditor.yaml`, in mancanza la
  cwd). **Facoltativo**: senza, il mondo funziona (contenuti) ma `supports_players` e' falso. Se il file SQLite non esiste i
  giocatori rispondono 503 `world.unavailable` (l'editor non crea mai un DB vuoto). La risposta HTTP e' generica: percorso e
  messaggi del driver restano nel log del server (e in `worlds check`, che e' locale).
- `config_path` (anche come chiave diretta del mondo): il `pachimud.yaml` del game server, letto con PyYAML (nessun import del
  gioco); se mancano `database_url`/`definitions_path` si usano `database_url` e `definition_path` di quel file, i cui path
  relativi si risolvono rispetto alla SUA cartella (cwd del game server). **I parametri espliciti vincono sempre.** Con il solo
  `config_path` (configurazione di mudedit) basta una riga.
- Ripiego documentato: senza `definitions_path` e senza `config_path` si usa la variabile d'ambiente `PACHIMUD_CONFIG_PATH`
  come `config_path`.

## Layout dei file e convenzioni

```
definitions/zones/<Zona>/zone.yaml            zone_id (slug), vnum, name, builder, description, bottom_vnum, top_vnum,
                                              max_level (livello massimo di accesso, default 50, non applicato),
                                              lifespan_minutes, reset_mode, enabled   (`min_level` non esiste piu': e' ignorato)
                         rooms*.yaml          rooms: [{vnum, name, description, sector_type, flags, heal_rate, mana_rate,
                                              clan_id, owner, enabled, area, exits: {north: {...}}, extra_descriptions: [...]}]
                         mobs*.yaml           mobs: [{vnum, keywords, ..., hp_dice "3d8+10", damage_dice, ...}]
                         objects*.yaml        objects: [{vnum, object_type, <campi del tipo>, ...}]
                         resets*.yaml         resets: {objects: [...], mobs: [...], doors: [...]}
definitions/classes/<id>.yaml, races/<id>.yaml, locales/<lingua>/messages.yaml
```

Come il loader del gioco: `zone.yaml` si cerca ricorsivamente sotto `zones/` e i file di contenuto nella stessa cartella
(`room*`, `mob*`, `obj*`, `reset*`). Un suffisso `_<area>` / `-<area>` nel nome (`rooms_nord.yaml`) e' l'**area** del file
(etichetta libera, esposta in `extra.area`, testo vuoto = nessuna area); un `area:` nel file o nella voce vince sul suffisso.

- **Identita'**: zona = `vnum` di `zone.yaml` (`id == vnum`); stanza/mob/oggetto = `vnum` globale (`id == vnum`); uscita =
  `vnum_stanza * 10 + direzione`; extra description = `vnum_stanza * 1000 + posizione`; comando di reset = posizione nello script.
- **Lettura tollerante**: un file YAML rotto o una voce non valida (campo mancante, enum errato, dadi `XdY+Z` malformati, oggetto con
  campi di un altro tipo...) producono un problema con file e riga, ma non fermano il mondo: il resto si legge. I problemi sono in
  `worlds check`, nel log all'avvio e in `GET /api/world/overview` (`fileProblems`). Una voce non valida resta nel file (non si
  cancella mai cio' che non si e' capito).
- **Scrittura**: solo le chiavi modificate (commenti, ordine e stile del file restano), scritte in modo atomico (file temporaneo
  nella stessa cartella + `os.replace`). Un valore uguale al default non viene aggiunto al file. Nei file di stanze, mob e oggetti la
  scrittura e' **selettiva**: cambiano nel testo solo le righe delle voci modificate, aggiunte o tolte (con i commenti attaccati sopra
  ciascuna), mentre le altre voci, i commenti fra le voci e il resto del file restano byte per byte come erano, anche i testi a capo
  su piu' righe. Il testo ottenuto e' riletto e confrontato con il documento; se non coincide (file con una forma insolita, come un
  trattino su una riga a parte) si ripiega sulla scrittura completa. `zone.yaml` e i file dei reset si scrivono sempre per intero.
- **Dove va una nuova entita'**: nel file base della zona (`rooms.yaml`, `mobs.yaml`, `objects.yaml`) o, con `extra.area`, nel file
  di quell'area (`rooms_<area>.yaml`); il file si crea se manca. Cambiare `zoneId` o `extra.area` sposta la voce nel file di
  destinazione. Una **zona nuova** e' una cartella `zones/<Nome>/` con il solo `zone.yaml` (`extra.folder` sceglie il nome, altrimenti
  si ricava dal nome della zona; 409 `pachimud.folder_exists` se c'e' gia'). Eliminare una zona (409 `zones.not_empty` se ha stanze,
  mob o oggetti) toglie `zone.yaml` e i suoi file `rooms*/mobs*/objects*/resets*.yaml` e la cartella se resta vuota.
- **Vnum duplicate**: il gioco le sovrascrive in silenzio; l'editor tiene la prima (in ordine di percorso) e segnala le altre
  (`duplicate_vnum`).

### Campi e `extra`

| Entita' | `extra` |
|---|---|
| zona | `zoneId` (slug di `zone.yaml`), `description`, `folder` (sola lettura), `climate` (`temperate`/`desert`/`arctic`, elenco a scelta: sceglie i messaggi del meteo), `prototypesOnly` (zona di soli prototipi: nessuna stanza ne' reset), `extendsZone` (vnum di una zona di un altro strato che questa estende) |
| stanza | `enabled`, `area`, `climate` (`temperate`/`desert`/`arctic`, elenco a scelta; vuoto = eredita quello della zona) |
| mob | `area`, `name`, `attacks`, `persona` (dialogo LLM), `strength`, `dexterity`, `constitution`, `intelligence`, `wisdom`, `charisma` (0 = non impostata), `postmaster` (impiegato postale), `receptionist` (rent e offer), `weaponImmunity` (0 = armi non magiche, 1-4 = fino a +N; vuoto = nessuna), `breath` (soffi: nomi liberi, es. `fire`, `frost`, `acid`, `gas`, `lightning`), `breathCost` (mana per soffio), `shop` (negozio, descritto nella nota su `extra.shop` qui di seguito), `triggers` (trigger del mob, vedi la nota su `extra.triggers`) |
| uscita | `isMale` (genere grammaticale del nome dell'uscita), `openCmd` (`pull`, `push`, `lift`, `turn`, `twist`, `dig`, `cut`: il comando che apre la porta al posto di `open`/`close`; vuoto = porta normale), `climb` (uscita da scalare con `climb`) |
| oggetto | `area`, `extraDescriptions` (lista di `{keywords, text}`), `scripts` (script dell'oggetto, vedi la nota su `extra.triggers`), `typeFields` (dict con i campi specifici del tipo, nomi snake_case del file: anche `corpse`, `permanent`, TRAP `triggers`/`damage`/`level`/`charges`) |

- Mob: `hp_dice`/`damage_dice` (`XdY+Z`) sono spezzati nei campi `hpDiceCount/hpDieSize/hpBonus` e `damageDice*`.
- `extra.triggers` (mob, stanza) ed `extra.scripts` (oggetto): i trigger (`triggers:` / `scripts:` del file, `docs/trigger.md` del gioco) come lista di `{type, argument, chance, actions}`. `type`: mob `speech|greet|give|random|death|fight|hitprcnt|act|tell|bribe`, oggetto `get|drop|wear|give|random`, stanza `enter|exit|speech|random` (in lettura il file puo' avere qualunque tipo: lo segnala `content.validate` con `trigger-type-not-allowed`; in scrittura un tipo non ammesso e' 422 `pachimud.invalid_choice`). `argument` e' una stringa (vuoto = qualsiasi; `hitprcnt`: percentuale 1-100, `bribe`: monete minime, entrambi obbligatori), `chance` un intero 1-100 (default 100). `actions` e' la lista ordinata, non vuota, di comandi (variabili `$n`, `$i`, `$t`, `$o`, `$$`) **oppure blocchi** `{if: {condizioni}, then: [azioni], else: [azioni]}` fino a 3 livelli. Le condizioni (tutte insieme) sono `chance`, `level`, `hp` (numero o confronto `">= 10"`), `sex` (`male|female|other`), `race`, `class`, `carries`, `is_player`, `who` (`n`|`i`; `i` solo nei mob) e, dalla fase 3, `time` (ora 0-23, numero o confronto), `is_night` e `is_fighting` (booleani), `has_effect` (nome come `AffectedByFlags`, senza distinzione di maiuscole; uno sconosciuto e' solo un avviso `trigger-effect-unknown` del controllo), `vnum` (numero o confronto); `time` o `vnum` non validi e un'ora fuori da 0-23 sono 422 `pachimud.invalid_entry`. Una chiave sconosciuta non e' scartata. Oggetti e stanze ammettono solo `mpecho`, `mpechoat`, `mpechoaround` (un comando MP vero in un loro trigger e' 422 `pachimud.invalid_entry`); i mob hanno anche `mptransfer`, `mpgoto`, `mpat`, `mpload mob|obj`, `mppurge`, `mpkill`, `mpforce` (sintassi in `docs/trigger.md` del gioco; li controlla `content.validate` con `trigger-command-invalid`, `trigger-room-missing`, `trigger-mob-missing`, `trigger-object-missing`). `triggers.max_spawned` (20, `pachimud.json`) e' un limite del gioco sugli `mpload`, non dell'editor. Dopo `zone.reload` i mob e gli oggetti gia' presenti usano i trigger nuovi senza essere rigenerati. In lettura e' sempre una lista (`[]` se non ce ne sono). In scrittura il file riceve solo i campi diversi dal default e, per ogni trigger, un valore equivalente a quello gia' nel file (anche con `chance: 100` scritto a mano) resta com'e' (commenti inclusi): un PUT invariato non da' diff, un salvataggio che non invia la chiave non la tocca, `[]` toglie la chiave. Errori: 422 `pachimud.invalid_choice` / `invalid_range` / `invalid_length` (campo `triggers[N].type|chance|actions[K].if.chance`), `pachimud.invalid_entry` per argomento di `hitprcnt`/`bribe` e per piu' di 3 `if` annidati. Nel frontend la sezione **Trigger** (mob, stanza) o **Script** (oggetto) li modifica con un editor ricorsivo (una riga per azione, blocchi **Se / Allora / Altrimenti** con condizioni tipizzate; razza e classe suggerite dai cataloghi) e mostra sotto ogni trigger i problemi `trigger-*`, `race-unknown` e `class-unknown` dell'ultimo controllo dei contenuti (nel messaggio del gioco, `<kind> <vnum>, trigger N` e' 0-based, anche per oggetti e stanze). Dalla pagina Controllo il click su un problema apre la voce giusta.
- Mob, `extra.shop`: il negozio (`shop:` del file, copia di `ShopProto` del gioco) come oggetto JSON con `produces` (vnum sempre in vendita),
  `trades` (tipi di oggetto comprati, nomi del gioco), `profit_buy`/`profit_sell`, `room`, `open1`/`close1`/`open2`/`close2` (ore 0-23,
  `28` = sempre), `no_money_reaction` (`puke`/`grin`/`none`), `attacked_reaction` (`warn`/`insult`/`none`), `messages` (per chiave e lingua,
  chiavi ammesse `no_such_item1`, `no_such_item2`, `do_not_buy`, `missing_cash1`, `missing_cash2`, `message_buy`, `message_sell`) e
  `handler` (hook Python). Si legge con tutti i campi (anche i default) e si scrive solo con quelli diversi dal default; un valore non
  valido e' 422 `pachimud.invalid_entry` e il file non cambia; `null` toglie il negozio. Il vecchio `shop_id` non fa piu' nulla.
- Oggetto: i tipi con campi propri sono WEAPON, `FIREWEAPON` (`strength`, `range_bonus`, `ammo_type`), `MISSILE` (`break_chance`,
  `dice_count`, `die_size`, `ammo_type`), ARMOR, CONTAINER, DRINKCON, FOOD, MONEY, KEY, AUDIO, TRAP e `BOARD` (`board_id`,
  `min_read_level`, `min_write_level`, `min_remove_level`, `max_messages`, `max_length`); `value0..3` di FIREWEAPON e MISSILE seguono gli
  indici di LeU.
- Oggetto: `objectType` e' l'`ObjectType` del core (i tipi del gioco: LIGHT, SCROLL, WAND, STAFF, WEAPON, FIREWEAPON, MISSILE,
  TREASURE, ARMOR, POTION, WORN, OTHER, TRASH, TRAP, CONTAINER, NOTE, DRINKCON = `LIQUID_CONTAINER`, KEY, FOOD, MONEY, PEN, BOAT,
  AUDIO, BOARD, TREE, ROCK, FOUNTAIN). Ogni voce del file ha SOLO i campi del suo tipo (`typeFields`: `dice_count`, `die_size`,
  `weapon_type`, `armor_class`, `spells`, `container_flags`, `liquid`...); cambiando tipo i campi del vecchio tipo che il nuovo non
  ha sono tolti dal file. `value0..3` sono **derivati** dagli indici di LeU per i soli campi numerici (es. WEAPON: v1 = `dice_count`,
  v2 = `die_size`, v3 = `weapon_type`; i campi con stringhe non hanno slot) e si possono ancora scrivere (conversioni da altri mondi);
  `extra.typeFields` prevale. I flag sono liste di stringhe libere: si conserva la maiuscola/minuscola del file. Le liste di scelta di stanze, mob e oggetti (`extra`/`wear`) vengono dal catalogo del gioco (`json-schema/flags.json`, copiato in `flags.json` dell'adapter e confrontato con il gioco da `test_flag_catalog_matches_the_game` quando `PACHIMUD_GAME_ROOT` è impostata; ricopiarlo dopo `pachimud json-schema`): `GET /api/meta/enums` ha `pachimudRoomFlags`, `pachimudMobFlags`, `pachimudObjectExtraFlags` e `pachimudObjectWearFlags`, con descrizione it/en, alias, origine e `implemented`; il form mostra «non ancora attivo» per i flag inerti. Un valore non in elenco si può comunque scrivere (il gioco lo segnala con `flag-unknown`). I nomi canonici sono maiuscoli; gli esistenti in minuscolo restano come sono. Il flag delle uscite è `doorFlag`.
- Uscite: `targetRoomId` e' `null` se la stanza di destinazione non esiste (resta il vnum in `targetRoomVnum`); una PATCH con
  `targetRoomId: null` su un'uscita gia' senza destinazione e' un no-op (per toglierla si elimina l'uscita). `isOpen`/`isLocked`
  sono dell'uscita stessa; lo stato porta al reset sta in `resets*.yaml` (`doors`).

### Script di reset

Il gioco descrive i reset come strutture annidate; l'editor li espone come lo script ROM M/O/G/E/P/D (stesso contratto degli altri
mondi): oggetto a terra = `O` + `P` per i `contains`; mob = `M` + `G` (inventario) / `E` (con `wear_slot`) + `P`; porta = `D`.
Ordine di emissione: oggetti, mob, porte. Salvando lo script (`PUT /zones/{id}/reset-commands`): se e' invariato non si scrive nulla;
altrimenti tutto va in `resets.yaml` e gli altri `resets*.yaml` della zona vengono svuotati (**i commenti dei reset non si
conservano**, e l'area per file si perde). `G`/`E` richiedono un `M` precedente e `P` un oggetto contenitore emesso dopo l'ultimo
`M`/`O` (422 `pachimud.reset_orphan`); `R` (rimescola le uscite) non esiste nel gioco (422 `pachimud.reset_unsupported`); `ifFlag`,
`ifValue`, commenti ed `extra` non sono rappresentabili (422 `world.extra_unsupported`). Se un file di reset e' illeggibile non lo si
sovrascrive (409 `pachimud.file_broken`).

## Integrita' e `worlds check`

L'editor segnala cio' che il gioco ignora in silenzio (`GET /api/world/overview`, `warnings`, `kind` stabili):
`exit_without_target` (destinazione assente **o inesistente**), `exit_key_missing`, `container_key_missing`, `reset_unknown_room|mob|object`,
`duplicate_vnum`, `vnum_out_of_range`, `room_empty_description`, `zone_empty_reset_script`, `mob_never_loaded`, `object_never_loaded`.
`pachimudeditor worlds check` mostra conteggi (stanze/mob/oggetti), lo stato del DB dei giocatori (revisione alembic, avvisi) e un
avviso per ogni file o voce non leggibile.

## Giocatori (DB)

`schema.py` riflette `account` e `player_character` e le mappa su classi minime con gli stessi nomi dei modelli del gioco
(`session.info["models"]`); `REVISIONS` e' la catena alembic del gioco (verificata da `tests/test_game_compat.py`, fino a `a7d1e5c9b3f4`; le migrazioni del gioco stanno in `src/pachimud/migrations/versions`)
e `EXPECTED` le colonne attese. Una colonna non essenziale assente (`language`, `inventory`) e' *non supportata* (valore neutro in lettura,
422 `world.field_unsupported` per un valore diverso in scrittura); tabella assente = `supports_players` falso; colonne essenziali assenti =
`incompatible` (503 `world.unavailable`). Lo schema si legge una volta per processo.

- `current_room_vnum` e' solo un vnum (nessuna FK): l'editor lo risolve con le stanze dei file (`currentRoomId == vnum`; se la stanza
  non esiste resta il vnum senza nome). Cancellare una stanza o cambiarne il vnum con personaggi dentro: 409 `rooms.has_instances`.
- `inventory` (JSON: lista di `{vnum, overrides, equipped_slot, state, contents}`) e' il formato deciso dal gioco, che oggi non lo scrive
  ne' lo legge: `/api/players/characters/{id}/inventory` lo mostra e lo modifica (`id` di una voce = posizione nella visita in
  profondita', instabile dopo aggiunte/rimozioni). Eliminare un personaggio porta via l'inventario (`cascade` non ha piu' effetto).
- `strength_percentile` non esiste piu' nel gioco: `strengthPercentile` vale sempre 0 e in scrittura e' ammesso solo 0.
- Password degli account: Argon2id con i parametri del gioco (`security.py`, dipendenza `argon2-cffi`).
- Interi: vnum e argomenti dei reset hanno `le=MAX_INT` (2^31-1); id/page/pageSize oltre i 64 bit di SQLite rispondono 422
  `world.value_out_of_range`.
- `player_character.position` e' salvato dal gioco come NOME dell'enum (colonna testuale) e l'editor fa lo stesso.

## Razze, classi e trasferimento

- Razze e classi (`definitions.py`, copie minime di `LoaderRace`/`LoaderClass`): `definitions/races`, `definitions/classes`, modificabili da
  `/api/content`; i file illeggibili sono saltati con un avviso nel log, le classi con `disabled: true` non sono caricate. L'uso
  (`mobCount`) viene dai mob dei file YAML.
- Trasferimento zone (`transfer/service.py`, `apps/transfer`): **esporta** la cartella di zona cosi' com'e' su disco (zip con tutti i suoi
  file, oppure JSON `files` nome -> testo); **importa** una cartella/zip con `zone.yaml` e `room*/mob*/obj*/reset*.yaml`: anteprima per vnum
  (create/update/unchanged, `keptNotInFile`), conflitti con altre zone (409 `transfer.vnum_conflict`) e avvisi (`dangling_exit`,
  `unknown_reset_ref`, `unknown_key`, `unknown_race|class`, `out_of_range`, `range_overlap`...). Applicazione: se la zona (per vnum)
  non esiste si copiano i file cosi' come sono in una nuova cartella; se esiste si fa l'upsert delle voci nei suoi file e si sostituisce lo
  script di reset (mai cancellazioni di stanze/mob/oggetti). Limiti dell'upload (`apps/transfer/archive.py`): al massimo 10 file/zip e
  200 voci in totale, 20 MB complessivi e 2 MB per ogni YAML (413 `transfer.file_too_large`); piu' zone nello stesso upload -> 422
  `transfer.multiple_zones`. Il parsing YAML gira fuori dal loop (threadpool).

## Limiti

- Il gioco **non ricarica a caldo**: le modifiche ai file valgono al riavvio, oppure subito con il canale live (`livectl`, vedi [canale live](pachimud-live.md)): «Ricarica nel gioco» nel dettaglio zona rilegge i YAML di una zona. Niente spawn/teleport dall'editor (il gioco non ha `load.*`).
- Un solo database per mondo; PostgreSQL & co. funzionano in teoria (SQLAlchemy async) ma sono provati solo su SQLite.
- Un campo nuovo dei YAML del gioco non compare nei DTO finche' non lo si aggiunge a `loaders.py`, a `mapping.py` (e a `fields.py`): un campo
  sconosciuto in un file resta intatto ma non e' visibile; negli oggetti, `extra="forbid"` rende non valida la voce (segnalata).
- L'indice delle voci si ricostruisce a ogni scrittura (nessun problema per mondi di qualche migliaio di voci).
- Ogni scrittura rilegge il file per verificarlo (vedi «Scrittura selettiva»): circa 250 ms per un `rooms.yaml` di 46 stanze (misurato prima della scrittura selettiva, non rimisurato). Una conversione da un altro mondo fa una scrittura per voce, quindi ~600 voci richiedono ~17 s: la pagina Converti mostra l'avanzamento e il test e2e attende fino a 90 s. Scrivere i file una volta sola a fine conversione richiederebbe un'API di scrittura a lotti nel motore di conversione, non ancora fatta.

# Mondi opzionali e pacchetto `pachimud`

- Nessun mondo e' implicito: i mondi sono solo quelli di `webeditor_worlds` (vuoto = `/api/worlds` vuoto, UI con la
  pagina "Nessun mondo configurato").
- `pachimud` (il gioco) NON e' una dipendenza (nemmeno di sviluppo) e nessun file del repo lo importa (lo verifica
  `tests/core/test_boundaries.py` con una scansione AST di src, adapter, tests, e2e e scripts, e `tests/test_bootstrap.py` con un processo `python -I` che blocca l'import).
  I loader YAML (`loaders.py`) e i modelli SQLAlchemy del DB (`game_models/`: `Account`, `PlayerCharacter`) sono COPIATI: l'adapter in produzione
  legge il DB con la riflessione e non usa i modelli, che servono a test, seed e2e e script per creare lo schema. Per questo
  `params.config_path` si limita a leggere il `pachimud.yaml` come YAML e non c'e' nessun `python_path`.
- Il confronto della copia con il MUD vero (hash, enum, loader, colonne, revisioni alembic, `definitions/` reali caricate senza errori e
  riscritte su una copia con gli stessi dati, file dell'editor validati dai loader del gioco) e' OPZIONALE: `tests/test_game_compat.py` gira
  solo se `PACHIMUD_GAME_ROOT` punta a un checkout del gioco (con `PYTHONDONTWRITEBYTECODE=1` e il `site-packages` del suo venv in `PYTHONPATH`),
  altrimenti e' saltato. I test sempre attivi (`tests/test_roundtrip.py`) verificano la riscrittura con gli stessi valori e il giro export -> import.
- `modules.build_modules(kinds)` aggiunge i moduli dei plugin dei kind configurati: `world/players/transfer/content` arrivano dal plugin
  pachimud e si registrano solo quando c'e' un mondo `kind: pachimud` (le pagine del frontend compaiono solo se il mondo ha la capability,
  `supportsWorldOverview/Players/Transfer/ContentRaces`).

## Range vnum delle zone

A differenza di basedmud/dikumod, in pachimud `bottom_vnum`/`top_vnum` di una zona sono metadati indicativi (il gioco non li impone;
`(0, 0)` = non assegnato) e stanze/mob/oggetti appartengono alla zona il cui file li contiene. Per questo creare o spostare un vnum
fuori range non e' rifiutato (nessun `vnum_out_of_range` in scrittura): lo segnala il controllo di integrita' del mondo (`/api/world`,
tipo `vnum_out_of_range`).

## Strati di contenuti e PostgreSQL (gioco al commit 9242b1e)

- Il gioco applica piu' strati di contenuti: classi, razze, tabelle e testi di default stanno nel pacchetto (`src/pachimud/definitions`), poi
  `definition_path` ed eventuali `extra_definition_paths`. L'editor tratta come strato di zone solo `definitions_path`; per classi e razze
  legge in piu' un primo strato di sola lettura, `params.base_definitions_path` (con `config_path` e un checkout del gioco si ricava da
  `<cartella del pachimud.yaml>/src/pachimud/definitions`). `/api/content` scrive sempre in `definitions_path`. Il campo `extends_zone`
  di `zone.yaml` e' esposto (`extra.extendsZone`), ma l'editor non fonde gli strati.
- `database_url` puo' essere PostgreSQL (`postgresql+asyncpg://...`, dipendenza `asyncpg`): `${VARIABILE}` si espande dall'ambiente come nel
  gioco (variabile mancante = errore chiaro) e `sslmode=` diventa `ssl=`. Istanti con fuso (UTC), `position` enum `position_type`.
- `player_character` ha in piu' `class_levels`, `move_current/max`, `height`, `weight`, `played_seconds`, `affects`, `affect_mods`, `speaks`,
  `poison_strength`, `description`: esposti in `CharacterDetail` e modificabili (tranne `affect_mods`, sola lettura). I valori predefiniti del
  gioco sono scritti anche per i record creati dall'editor (`EXPECTED`).
- `Position` ha i nomi del gioco (`MORTALLY_WOUNDED`, `INCAPACITATED`, `MOUNTED`=9).

## Skill, social, tabelle e cataloghi (strati)

Oltre a razze e classi l'editor modifica, da `/api/content` (`docs/backend/contract-content.md`), le skill (`skills/<id>.yaml`), i social
(`tables/socials*.yaml`), le tabelle (`tables/*.yaml`: punteggi, liquidi, forme di `polymorph self`, pose), i cataloghi dei messaggi
(`locales/<lingua>/**/*.yaml`) e i testi lunghi (`texts/*.txt`). Il gioco applica piu' strati (pacchetto, poi `definition_path`): l'editor legge
`base_definitions_path` + `definitions_path` e **scrive solo nello strato dell'utente** (un contenuto di serie diventa «tuo» al primo salvataggio;
eliminarlo dallo strato dell'utente ripristina quello di serie). Con `config_path` la base si ricava da `<cartella del pachimud.yaml>/src/pachimud/definitions`;
se il gioco gira altrove (o usa `extra_definition_paths`) indicare `base_definitions_path` a mano: le cartelle extra non sono lette (`worlds check` e il log lo segnalano con l'avviso `extra_definition_paths_ignored`).
Nel frontend: pagine **Skill**, **Social** (maschere inline con i testi per lingua), **Tabelle** e **Cataloghi e testi** (testo YAML/TXT inline). Le skill hanno
un form per i campi semplici e un campo YAML per `levels`, `effects`, `handler`, `messages`, ... Il form non conosce tutti gli id: il controllo dei riferimenti e' del gioco.
Dopo ogni salvataggio, con il canale live connesso, l'editor chiede al gioco `content.validate` e mostra i problemi (gravita', codice, messaggio, file e riga);
«Controlla i file» lo rifa' a richiesta e «Ricarica nel gioco» chiama `content.reload`.


## Negozi

Nel frontend la scheda **Negozio** del dettaglio mob (sezione dopo «Ruoli e servizi») modifica il campo `shop:` del mob: merci sempre in vendita (cercate per nome fra gli oggetti), tipi
comprati, margini (con la percentuale pagata), stanza, orari (`28` = sempre aperto), reazioni, messaggi per lingua (it/en) e hook Python. La pagina **Negozi** (`/shops`) elenca tutti i
negozianti con ricerca, «Controlla i file» (`content.validate`, codici `shop-*` nel pannello dei problemi) e «Ricarica la zona nel gioco» (`zone.reload`) per applicare le modifiche al gioco
acceso. Un mob con il vecchio `shop_id` e senza `shop` e' segnalato (il gioco lo ignora); si risolve attivando «Il mob e' un negoziante». Contratto: `backend/contract-content.md`.

## Locande

Una locanda e' un mob con `receptionist: true`: con lui nella stanza i giocatori usano `offer` e `rent` (costi e rifiuti fissi come in LeU, non configurabili da YAML). Nel dettaglio mob la sezione **Locanda**
mostra il flag con la spiegazione. La pagina **Locande** (`/inns`) elenca tutti i locandieri con ricerca, segnala quelli che nessun reset carica in una stanza (o che puntano a una stanza inesistente),
ha «Controlla i file» (`content.validate`), «Ricarica la zona nel gioco» (`zone.reload`, solo con il canale live connesso, la scrittura consentita e il comando dichiarato) e «Nuovo locandiere» (mob receptionist da
template nella zona scelta; con la stanza facoltativa aggiunge anche il reset `M` che lo carica, nello script della zona della stanza: se e' diversa da quella del mob lo si segnala). Contratto: `backend/contract-content.md`.

## Skill: nome italiano e dove può stare

Nel form della skill il campo **Dove può stare** (`item_types`: pozione, pergamena, bacchetta, bastone, unguento) dice in quali oggetti l'incantesimo può stare; vuoto = nessun vincolo. Un salvataggio che non lo tocca
lo lascia com'è (anche una lista vuota scritta a mano nel file, che nel gioco vuol dire «in nessun oggetto»); valori diversi da quelli elencati danno 422 `content.invalid`. Il nome mostrato ai giocatori (`messages.name`,
per lingua) e' a sola lettura (in elenco e accanto al titolo della scheda): si modifica fra i campi avanzati (YAML). Nel dettaglio di una pozione, pergamena, bacchetta o bastone un riquadro avvisa se un incantesimo
citato (`extra.typeFields.spells`, `extra.typeFields.spell`) non esiste fra le skill o se la sua `item_types` non ammette quel tipo: sono gli stessi controlli di `skill-unknown` e `item-spell-not-allowed` del gioco, ma senza il canale live.
Le traduzioni a parte (`skills/<id>.<lingua>.yaml`) non entrano in `names`.

## Controllo dei contenuti e consigli di stile

La pagina **Controllo** (`/content/check`, capability `supports_content_races`) chiede al gioco `content.validate` (anche in versione **severa**, con il pulsante «Controllo severo») e
mostra i problemi **raggruppati per codice**, ognuno con la sua spiegazione (it/en): controlli di zona (`exit-one-way`, `room-unreachable`, `door-state-mismatch`, `door-no-keywords`,
`mob-never-loaded`, `object-never-loaded`, `reset-max-low`, `exit-target-out-of-zone`), lint di stile (`style-*`), flag, valori, negozi. Un problema il cui file e' dell'editor e' cliccabile e apre la
stanza, il mob, l'oggetto, i reset o la zona: l'adapter risolve `file:riga` sulla voce che comincia alla riga piu' vicina prima (`POST /api/content/checks/locate`; il percorso si cerca prima uguale,
poi dal ramo `zones/<zona>/<file>`, quindi funziona anche se il gioco gira da un'altra copia). Il menu «Zona» limita l'elenco a una zona.
Nelle schede di stanza, mob e oggetto un riquadro **Consigli di stile** (non blocca il salvataggio) e il contatore dei caratteri nei campi titolo, corta e lunga ripetono le regole di stile con le soglie
del mondo: `GET /api/content/checks/style` legge la sezione `validate.style` del `pachimud.yaml` (`config_path`) sui default del manuale di Clessidra. La fonte della verita' resta `content.validate`.

## Bacheche e posta

La pagina **Bacheche** (`/boards`, capability `supports_boards`, sola lettura) elenca gli oggetti BOARD dei YAML (`board_id`, o il vnum se manca, come fa il gioco) e i `board_id` che hanno
messaggi nel DB (`board_message`) anche senza oggetto (badge «senza oggetto»), con il conteggio. Un clic apre i messaggi (autore, data, titolo, testo) con ricerca; il numero mostrato e' quello con cui
li legge il gioco. La scheda **Posta** mostra solo quante lettere aspettano ogni giocatore (`mail_message`): il testo non viene mai letto. Se una tabella manca (schema del gioco non aggiornato) la pagina
lo dice e propone `pachimud db upgrade`. Cancellare un messaggio («Cancella il messaggio», con conferma) o svuotare una bacheca («Svuota la bacheca») passa sempre dal canale live (`board.delete`, `board.clear`, con `allow_write`): il gioco
tiene i messaggi in memoria (`BoardStore`, caricata una volta sola) e il loro numero e' la posizione nella lista, quindi l'editor non scrive mai su `board_message`. Senza canale connesso la pagina e' in sola lettura e lo dice. Contratto: `backend/contract-content.md`.
