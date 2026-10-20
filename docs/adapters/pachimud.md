# Adapter pachimud (`kind: pachimud`, database SQLAlchemy letto "al volo")

L'editor ha un database SUO (utenti/opzioni, pachifast) separato da quelli dei MUD: le connessioni ai MUD le gestiscono gli
adapter. `PachimudAdapter` NON importa il pacchetto `pachimud`: apre il database di gioco con SQLAlchemy async (aiosqlite
per SQLite) e **riflette le tabelle reali** (`MetaData.reflect`) invece di usare i modelli ORM del gioco.

## Parametri del mondo

```yaml
webeditor_worlds:
  - id: pachimud
    kind: pachimud
    name: Pachimud
    params:
      database_url: sqlite+aiosqlite:///pachimud.db   # URL SQLAlchemy async (o altro driver async)
      definitions_path: ./definitions                 # races/, classes/ (e zones/); facoltativo
      config_path: /percorso/pachimud.yaml            # facoltativo: il pachimud.yaml del game server
```

- `database_url`: un URL senza driver async e' portato al driver async di default (`sqlite://` -> `sqlite+aiosqlite://`).
  I path SQLite relativi si risolvono rispetto alla cartella di lavoro (la cartella del `pachimudeditor.yaml`, in mancanza la
  cwd). Se il file SQLite non esiste il mondo risponde 503 `world.unavailable` (l'editor non crea mai un DB vuoto). La risposta HTTP e' generica: percorso e messaggi del driver
  restano nel log del server (e in `worlds check`, che e' locale).
- `definitions_path`: cartella `definitions/` (razze e classi YAML; `zones/` e' solo il formato di scambio). Assente =
  `supports_content_races` falso, `/api/meta/races|classes` vuote.
- `config_path` (anche come chiave diretta del mondo): il `pachimud.yaml` del game server, letto con PyYAML (nessun import del
  gioco); se mancano `database_url`/`definitions_path` si usano `database_url` e `definition_path` di quel file, i cui path
  relativi si risolvono rispetto alla SUA cartella (cwd del game server). **I parametri espliciti vincono sempre.**
- Ripiego documentato: senza `database_url` e senza `config_path` si usa la variabile d'ambiente `PACHIMUD_CONFIG_PATH`
  come `config_path`. Senza nulla di tutto cio' l'avvio fallisce con un errore chiaro (`WorldSetupError`).

## Architettura

- `params.py` risolve i parametri; `connection.py` possiede l'engine/sessionmaker del mondo (creati al primo uso, chiusi
  da `PachimudAdapter.close()`/`registry.aclose_all()` allo spegnimento) con i pragma SQLite del gioco (`busy_timeout`, WAL,
  `foreign_keys=ON`). `schema.py` riflette le tabelle (`zone`, `room`, `exit`, `room_extra_description`, `mob_prototype`,
  `object_prototype`, `zone_reset_command`, `mob_instance`, `object_instance`, `account`, `player_character`,
  `alembic_version`) e mappa su ciascuna una classe minima (mapping imperativo, senza relazioni) con gli stessi nomi dei modelli del
  gioco; le classi stanno in `session.info["models"]` (`models_of(session)`), una serie per mondo: due mondi pachimud con
  schemi diversi non si disturbano.
- Il significato delle colonne intere sta nelle tabelle dati dell'editor (`common/enums.py`, `pachimudeditor_adapter_pachimud/race_enums.py`);
  `player_character.position` e' salvato dal gioco come NOME dell'enum (colonna testuale) e l'editor fa lo stesso.
- Nessuna cascade nel DB (le FK non hanno `ON DELETE`): cancellare una stanza azzera esplicitamente `exit.target_room_id`
  delle uscite entranti e cancella uscite/extra description; una zona cancella il suo script di reset; le regole di
  integrita' sono quelle di `rules.py` (reset/chiavi/istanze).
- Password degli account: Argon2id con i parametri del gioco (`pachimudeditor_adapter_pachimud/security.py`, dipendenza `argon2-cffi`):
  gli hash dell'editor si verificano nel gioco e viceversa.
- Razze e classi: parser Pydantic propri (`definitions.py`, copie minime di `LoaderRace`/`LoaderClass`); i file illeggibili
  sono saltati con un avviso nel log, le classi con `disabled: true` non sono caricate.
- Trasferimento zone (`pachimudeditor_adapter_pachimud/transfer/`): `schemas.py` (copie dei `Loader*`), `files.py` (writer dei cinque file
  `zone/rooms/mobs/objects/resets.yaml`), `importer.py` (upsert per vnum come l'importer del gioco), `preview.py` (dry-run).
  Limiti dell'upload (`apps/transfer/archive.py`, `importer.py`): al massimo 10 file/zip e 200 voci di zona in totale, 20 MB complessivi
  e 2 MB per ogni YAML (413 `transfer.file_too_large`), 5000 record per file (422 `transfer.invalid_file`); piu' zone nello stesso upload
  -> 422 `transfer.multiple_zones`. Il parsing YAML gira fuori dal loop (threadpool) e le query `IN` sono a blocchi.
- Interi: vnum e argomenti dei reset hanno `le=MAX_INT` (2^31-1, `common/adapters/models.py`); id/page/pageSize oltre i 64 bit di SQLite
  rispondono 422 `world.value_out_of_range` (rete di sicurezza in `PachimudSupport.session()`).

## Controllo di compatibilita' dello schema

All'apertura del mondo si legge `alembic_version` e si confronta con la tabella delle revisioni note
(`REVISIONS` in `schema.py`: `64f2026e1334` -> `f8c896cb5dd8` -> `848330e8786f` -> `9d4aa2f29079`, allineata alle migration del
gioco da `tests/test_game_compat.py`) e con le colonne attese di ogni tabella (`EXPECTED`). Il rapporto (`SchemaReport`) ha uno
stato: `ok`, `behind` (revisione nota piu' vecchia), `unknown` (revisione ignota), `unversioned` (niente `alembic_version`),
`incompatible`. Si scrive nel log all'avvio e `pachimudeditor worlds check` lo mostra (revisione, stato, avvisi). **Mai un
errore salvo `incompatible`**:

| Situazione | Effetto |
|---|---|
| revisione ignota / senza `alembic_version` | avviso nel log e in `worlds check`; si prosegue |
| colonna non essenziale assente (`race_id`, `class_id`, `arg_str`, `heal_rate`, `mana_rate`, `clan_id`, `owner`, `min_level`, `max_level`, `arg4`, ...) | il campo e' *non supportato*: `describe()` lo marca `unsupported` (sola lettura); in lettura vale il valore neutro; in scrittura e' accettato solo il neutro (422 `world.field_unsupported`); l'import YAML lo ignora con un avviso `unsupported_column` |
| tabella opzionale assente (`account`/`player_character`/`object_instance`, `mob_instance`, `room_extra_description`) | la capability collegata (`supports_players`, `supports_instances`, `supports_extra_descriptions`) e' falsa |
| colonna NOT NULL sconosciuta senza default | avviso (gli inserimenti potrebbero fallire); colonne sconosciute nullable: ignorate |
| tabella obbligatoria o colonna essenziale (chiavi, `vnum`, `direction`, ...) assente | `incompatible`: 503 `world.unavailable` su quel mondo, gli altri funzionano |

Lo schema si legge una volta per processo (riavviare l'editor dopo una migration del gioco).

## Limiti

- Un solo database per mondo; PostgreSQL & co. funzionano in teoria (SQLAlchemy async) ma sono provati solo su SQLite.
- Il game server tiene le istanze in memoria: modificare istanze/giocatori a server fermo.
- I default Python del gioco (`default=list`, `default=True`, ...) sono replicati in `EXPECTED` per gli inserimenti; un nuovo
  default Python aggiunto al gioco e' coperto solo se la colonna ha anche un default nel DB.
- Un campo nuovo del gioco non compare nei DTO finche' non lo si aggiunge a `common/adapters/models.py` e a `EXPECTED`.

# Mondi opzionali e pacchetto `pachimud`

- Nessun mondo e' implicito: i mondi sono solo quelli di `webeditor_worlds` (vuoto = `/api/worlds` vuoto, UI con la
  pagina "Nessun mondo configurato").
- `pachimud` (il gioco) NON e' una dipendenza (nemmeno di sviluppo) e nessun file del repo lo importa (lo verifica
  `tests/core/test_boundaries.py` con una scansione AST di src, adapter, tests, e2e e scripts, e `tests/test_bootstrap.py` con un processo `python -I` che blocca l'import).
  I modelli SQLAlchemy del DB di gioco sono COPIATI in `pachimudeditor_adapter_pachimud/game_models/`: l'adapter in
  produzione legge il DB con la riflessione e non li usa, servono a test, seed e2e e script per creare lo schema. Per
  questo `params.config_path` si limita a leggere il `pachimud.yaml` come YAML e non c'e' nessun `python_path`.
- Il confronto della copia con il MUD vero (hash, enum, schemi dei file, colonne, revisioni alembic, import di zone nei due
  versi) e' OPZIONALE: `tests/test_game_compat.py` gira solo se `PACHIMUD_GAME_ROOT` punta a un checkout del gioco, altrimenti
  e' saltato. I test sempre attivi (`tests/test_roundtrip.py`) verificano la coerenza con i modelli copiati.
- `modules.build_modules(kinds)` aggiunge i moduli dei plugin dei kind configurati: `world/players/instances/transfer/content`
  arrivano dal plugin pachimud e si registrano solo quando c'e' un mondo `kind: pachimud` (le pagine del frontend compaiono
  solo se il mondo ha la capability, `supportsWorldOverview/Instances/Players/Transfer/ContentRaces`).

## Range vnum delle zone

A differenza di basedmud/dikumod, in pachimud `bottom_vnum`/`top_vnum` di una zona sono metadati consultivi (il modello di
gioco non li impone come vincolo, come `min_vnum`/`max_vnum` in ROM; `(0, 0)` = non assegnato) e stanze/mob/oggetti non hanno
una zona di appartenenza esplicita. Per questo creare o spostare un vnum fuori range non e' rifiutato (nessun
`vnum_out_of_range` in scrittura): lo segnala il controllo di integrita' del mondo (`/api/world`, tipo `vnum_out_of_range`).
