"""Razze e classi di un mondo pachimud: i YAML di `definitions/races` e `definitions/classes`.

I modelli sono copie minime di `LoaderRace`/`LoaderClass` del gioco (`character/{race,classes}/schema/`): stessi campi
e default, cosi' un file valido per il gioco lo e' anche qui. `read_races`/`read_classes` riproducono il caricamento di
`RaceManager`/`ClassManager` (solo i `*.yaml`, `.yaml.disabled` esclusi) ma in modo tollerante: un file illeggibile
viene saltato con un avviso nel log invece di far fallire tutto. Le classi con `disabled: true` non sono caricate.
"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
import yaml

log = logging.getLogger(__name__)


class Stats(BaseModel):
    """Le sei caratteristiche."""

    strength: int = 0
    dexterity: int = 0
    constitution: int = 0
    intelligence: int = 0
    wisdom: int = 0
    charisma: int = 0


class LoaderRace(BaseModel):
    """Una razza (`definitions/races/<id>.yaml`)."""

    race_id: str
    name: str
    description: str
    mob_only: Optional[bool] = False
    mob_flags: Optional[list[str]] = []
    offensive_flags: Optional[list[str]] = []
    immunity: Optional[list[str]] = []
    resistance: Optional[list[str]] = []
    vulnerability: Optional[list[str]] = []
    form: Optional[list[str]] = []
    actual_form: Optional[list[str]] = []
    parts: Optional[list[str]] = []
    affected_by: Optional[list[str]] = []
    class_mult: Optional[list[int]] = []
    skills: Optional[list[str]] = []
    stats: Optional[Stats] = None
    max_stats: Optional[Stats] = None
    extra_training_cap: Optional[int] = 0
    size: Optional[str] = "MEDIUM"
    who_name: Optional[str] = ""
    points: Optional[int] = 0
    class_multiplier: Optional[list[int]] = []
    start_room: Optional[int] = None


class LoaderClass(BaseModel):
    """Una classe (`definitions/classes/<id>.yaml`)."""

    class_id: str = ""
    disabled: Optional[bool] = False
    abbreviation: str = ""
    name: str = ""
    description: str = ""
    add_strength: Optional[bool] = None
    attrs_priority: list[str] = []
    attr_prime: str = ""
    thac0_00: int = 0
    thac0_32: int = 0
    hp_min: int = 0
    hp_max: int = 0
    weapon: int = 0
    skill_adept: int = 0


def load_yaml(path: Path, model: type[BaseModel]) -> BaseModel:
    """Legge e valida un file YAML (parser sicuro)."""
    return model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _read(directory: Path, model: type[BaseModel], id_field: str) -> dict[str, BaseModel]:
    """`{id: modello}` dei `*.yaml` della cartella; i file non validi sono saltati (avviso nel log)."""
    found: dict[str, BaseModel] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.yaml")):
        try:
            item = load_yaml(path, model)
        except Exception as exc:  # noqa: BLE001 - YAML/schema non validi: si salta il file
            log.warning("Definizione ignorata (%s): %s", path.name, str(exc).splitlines()[0][:200])
            continue
        found[str(getattr(item, id_field))] = item
    return found


def read_races(definitions: Path | None) -> dict[str, LoaderRace]:
    """Le razze caricabili, per `race_id`."""
    return _read(definitions / "races", LoaderRace, "race_id") if definitions else {}  # type: ignore[return-value]


def read_classes(definitions: Path | None) -> dict[str, LoaderClass]:
    """Le classi caricabili (non `disabled`), per `class_id`."""
    if not definitions:
        return {}
    classes = _read(definitions / "classes", LoaderClass, "class_id")
    return {key: value for key, value in classes.items() if not value.disabled}  # type: ignore[attr-defined,misc]
