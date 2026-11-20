# Contribuire

## Ambiente di sviluppo

Il progetto usa [uv](https://docs.astral.sh/uv/) per Python e pnpm per il frontend.

```bash
git clone https://github.com/ellethee/pachimudeditor.git && cd pachimudeditor
uv sync --all-packages                   # workspace: core + adapter editabili, con il gruppo dev (pytest)
(cd frontend && pnpm install)
uv run pachimudeditor init --workdir .   # la cartella del repo e' anche la cartella di lavoro
uv run pachimudeditor serve --workdir . --reload
```

Richiede Python 3.14. Type hints e docstring su ogni funzione. I dettagli (porte, variabili dei test, dati dei MUD)
sono nel `README.md` del repository.

## Test e qualita'

```bash
uv run pytest -q                  # suite completa (nessun checkout del MUD richiesto)
uv run pytest tests/core -q       # solo il core, senza adapter
uv run ruff check . && uv run ruff format --check .
(cd frontend && pnpm run typecheck)
```

### Dati reali dei MUD (opzionali)

La suite gira **senza** dati dei MUD: i test di scrittura, round trip, conversione e contratto usano mondi sintetici e
versionati (contenuti inventati, `tests/support/synthetic_worlds.py`). I test che asseriscono su contenuti precisi di dati
reali sono marcati `real_rom` / `real_dikumod` e vengono saltati se i dati mancano; per eseguirli (sola lettura, si lavora
su copie temporanee e a fine sessione si verifica che gli originali siano intatti):

| Variabile | Significato |
|---|---|
| `BASEDMUD_AREA_DIR` | cartella `area/` di basedmud (default: `../basedmud/area` accanto al repository) |
| `DIKUMOD_LIB` | cartella `lib/` dei dati di Diku Modificato (solo DikuMod1, "leu"); default `/dati/luca/muds/leu/lib` se esiste (senza, i test `real_dikumod` si saltano) |
| `DIKUMOD_PREFIX` | prefisso dei file dati (`<prefisso>.wld`, ...); default `leudata` se i file di `leu` esistono, altrimenti `dikumoddata`: **con dati di un'altra cartella serve il valore esatto** perche' i test non trovino i file mancanti |
| `DIKUMOD_SRC` | radice del progetto Diku Modificato (`Makefile`, `src/`, `lib/`), usata da `tests/live` per costruire il MUD su una copia; default `/dati/luca/muds/leu` |
| `PACHIMUD_GAME_ROOT` | checkout del MUD pachimud per il confronto dei loader YAML e dei modelli (test `tests/test_game_compat.py`, vedi «Riallineare i loader YAML») |

```bash
# default: usa la cartella ufficiale /dati/luca/muds/leu (sola lettura) e ../basedmud/area
uv run pytest -q -rs
# oppure con percorsi espliciti
DIKUMOD_LIB=/percorso/leu/lib DIKUMOD_PREFIX=leudata DIKUMOD_SRC=/percorso/leu BASEDMUD_AREA_DIR=/percorso/basedmud/area uv run pytest -q -rs
```

`-rs` elenca i test saltati col motivo. La CI fallisce se i test saltati superano `MAX_SKIPPED` (`.github/workflows/ci.yml`):
dopo aver aggiunto fixture sintetiche o test, aggiorna la soglia al nuovo valore (con un piccolo margine).

## Riallineare i loader YAML

Il MUD pachimud non e' una dipendenza. Dal commit `e958b4e` i suoi contenuti (zone, stanze, mob, oggetti, reset) sono file YAML e il DB
tiene solo account e personaggi: l'editor ne tiene una **copia** dei loader Pydantic in
`adapters/pachimud/src/pachimudeditor_adapter_pachimud/loaders.py` (da `zone/schema/loader_zone.py`,
`zone/room/schema/loader_room.py`, `mob/schema/loader_mob.py`, `object/schema/loader_object.py`), di razze/classi in `definitions.py`, dei modelli SQLAlchemy
`Account`/`PlayerCharacter` in `game_models/` e le definizioni di esempio (razze, classi, zona `RavnFjord`) in
`tests/fixtures/pachimud_definitions/`. Quando il MUD cambia formato:

1. riallinea `loaders.py` (stessi campi, default e validatori; `extra="forbid"` sugli oggetti) e, se serve, `definitions.py`, le enum in
   `common/enums.py` / `race_enums.py` e le copie di `game_models/{account,character}.py`;
2. se cambia il significato di un campo aggiorna `mapping.py` (voce YAML <-> DTO, `VALUE_SLOTS` per i `value0..3` degli oggetti) e `fields.py`
   (chiavi di `extra`); per una nuova revisione alembic aggiorna `REVISIONS`/`EXPECTED` in `schema.py`;
3. ricopia le definizioni di esempio da `definitions/` del MUD in `tests/fixtures/pachimud_definitions/`;
4. verifica con un checkout a portata di mano (le dipendenze del MUD devono essere importabili, ad es. con `PYTHONPATH` sul
   `site-packages` del suo `.venv`; **`PYTHONDONTWRITEBYTECODE=1`** per non scrivere nel checkout):
   `PYTHONDONTWRITEBYTECODE=1 PACHIMUD_GAME_ROOT=/percorso/pachimud uv run pytest tests/test_game_compat.py`
   (confronta enum, loader, colonne attese, catena alembic, carica senza errori le `definitions/` reali, le riscrive su una copia con gli
   stessi dati e fa validare i file scritti dall'editor ai loader del gioco; senza la variabile i test sono saltati e la CI non ne ha bisogno);
5. `uv run pytest -q` deve restare verde senza gioco.

## Questa documentazione

```bash
uv run --group docs mkdocs serve             # anteprima su http://127.0.0.1:8000
uv run --group docs mkdocs build --strict    # come la CI: un link o una pagina fuori dalla nav fanno fallire
```

`changelog.md` e `releasing.md` non sono file di `docs/`: li aggiunge `scripts/mkdocs_hooks.py` leggendo
`CHANGELOG.md` e `RELEASING.md` dalla radice. Il workflow `.github/workflows/docs.yml` pubblica il sito su GitHub Pages a
ogni push su `main` che tocca la documentazione e lo costruisce soltanto sulle pull request.

## Commit e rilasci

Commit in stile [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`...), suite verde,
`CHANGELOG.md` aggiornato per le modifiche visibili. Versioni, tag e pubblicazione dei cinque pacchetti sono in
[Rilasci](releasing.md).
