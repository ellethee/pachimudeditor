"""Nessun rinvio testuale morto nella documentazione ("vedi sezione X", "vedi sopra/sotto"): serve un link MkDocs."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
DEAD = re.compile(r"\bvedi\s+(?:la\s+)?(?:sezione|paragrafo|capitolo|sopra|sotto)\b", re.IGNORECASE)


def test_no_dead_textual_references() -> None:
    """Ogni rinvio interno e' un link `[testo](pagina.md#ancora)`; `mkdocs build --strict` (CI) ne verifica la validita'."""
    found = [
        f"{p.relative_to(DOCS)}:{n}: {line.strip()[:80]}"
        for p in DOCS.rglob("*.md")
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if DEAD.search(line)
    ]
    assert not found, "\n".join(found)
