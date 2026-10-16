# Contribuire

## Ambiente di sviluppo

Il progetto usa [uv](https://docs.astral.sh/uv/) per Python e pnpm per il frontend.

```bash
git clone https://github.com/ellethee/pachimudeditor.git && cd pachimudeditor
uv sync --all-packages                   # workspace: core + adapter editabili, con il gruppo dev (pytest)
uv pip install -e ../pachimud            # a mano: il gioco non e' una dipendenza (serve ai test di equivalenza)
(cd frontend && pnpm install)
uv run pachimudeditor init --workdir .   # la cartella del repo e' anche la cartella di lavoro
uv run pachimudeditor serve --workdir . --reload
```

Richiede Python 3.14. Type hints e docstring su ogni funzione. I dettagli (porte, variabili dei test, dati dei MUD)
sono nel `README.md` del repository.

## Test e qualita'

```bash
uv run pytest -q                  # suite completa (richiede il pacchetto pachimud)
uv run pytest tests/core -q       # solo il core, senza adapter ne' gioco
uv run ruff check . && uv run ruff format --check .
(cd frontend && pnpm run typecheck)
```

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
