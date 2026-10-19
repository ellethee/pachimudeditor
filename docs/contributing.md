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
