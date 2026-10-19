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
| `DIKUMOD_ROOT` | cartella che contiene `dikumod/lib` e `dikumod2/lib` (senza, i test `real_dikumod` si saltano) |
| `DIKUMOD_PREFIX` | prefisso dei file dati reali (default `dikumoddata`); i dati locali ne usano un altro: **senza il valore esatto i test sui dati reali falliscono** perche' non trovano i file |
| `PACHIMUD_GAME_ROOT` | checkout del MUD pachimud per il confronto dei modelli (test `tests/test_game_compat.py`) |

```bash
DIKUMOD_ROOT=/percorso/radice DIKUMOD_PREFIX=prefissolocale BASEDMUD_AREA_DIR=/percorso/basedmud/area uv run pytest -q -rs
```

`-rs` elenca i test saltati col motivo. La CI fallisce se i test saltati superano `MAX_SKIPPED` (`.github/workflows/ci.yml`):
dopo aver aggiunto fixture sintetiche o test, aggiorna la soglia al nuovo valore (con un piccolo margine).

## Mantenere i modelli allineati col MUD

Il MUD pachimud non e' una dipendenza: i modelli SQLAlchemy del suo database sono **copiati** in
`adapters/pachimud/src/pachimudeditor_adapter_pachimud/game_models/` (intestazione in ogni file con la provenienza) e le
definizioni di esempio in `tests/fixtures/pachimud_definitions/`. Quando il MUD cambia schema:

1. ricopia i file corrispondenti di `pachimud/{database,account,character,mob,object,zone}` (stessa mappa dell'intestazione),
   rimuovendo i metodi che usano il game server e correggendo gli import verso `game_models`;
2. aggiorna `EXPECTED`/`REVISIONS` in `adapter .../schema.py` e le enum in `common/enums.py` / `race_enums.py` se serve;
3. verifica con un checkout a portata di mano (le dipendenze del MUD devono essere importabili, ad es. con
   `PYTHONPATH` sul `site-packages` del suo `.venv`; `PYTHONDONTWRITEBYTECODE=1` per non scrivere nel checkout):
   `PACHIMUD_GAME_ROOT=/percorso/pachimud uv run pytest tests/test_game_compat.py`
   (confronta enum, schemi dei file YAML, colonne attese, catena alembic e import di zone con il MUD vero; senza la
   variabile i test sono saltati e la CI non ne ha bisogno);
4. `uv run pytest -q` deve restare verde senza gioco.

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
