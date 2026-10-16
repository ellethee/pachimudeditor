"""Giornale delle conversioni: un file JSON per esecuzione (piano + esito) in una cartella configurabile.

Cartella: variabile d'ambiente `WEBEDITOR_CONVERT_JOURNAL_DIR` oppure chiave `webeditor_convert_journal_dir` di
`pachimudeditor.yaml`. Se non e' impostata il giornale e' disattivato (la risposta lo dichiara in `journal.enabled`).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pachimudeditor.common.adapters.convert.models import ConvertPlan, ConvertReport, JournalInfo


def journal_dir() -> Path | None:
    """La cartella del giornale dalla configurazione (`None` = disattivato)."""
    value = os.environ.get("WEBEDITOR_CONVERT_JOURNAL_DIR")
    if not value:
        from pachifast.config.yaml_source import load_config_data

        value = load_config_data().get("webeditor_convert_journal_dir")
    return Path(str(value)).expanduser() if value else None


def write_journal(directory: Path | None, plan: ConvertPlan, report: ConvertReport) -> JournalInfo:
    """Scrive il giornale (se `directory` e' valorizzata) e restituisce `JournalInfo`; un errore di I/O non fa fallire la conversione."""
    if directory is None:
        return JournalInfo(enabled=False)
    stamp = datetime.now(timezone.utc)
    name = f"convert-{stamp:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.json"
    document = {
        "at": stamp.isoformat(),
        "sourceWorld": report.source_world,
        "targetWorld": report.target_world,
        "plan": plan.model_dump(by_alias=True),
        "report": report.model_dump(by_alias=True),
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return JournalInfo(enabled=True, file=None)
    return JournalInfo(enabled=True, file=name)
