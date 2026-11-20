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


class BodyRange(BaseModel):
    """Altezza (cm) e peso (kg) di un personaggio nuovo: un valore a caso fra minimo e massimo."""

    height: tuple[int, int]
    weight: tuple[int, int]


class RaceBody(BaseModel):
    """Altezza e peso per sesso."""

    male: BodyRange
    female: BodyRange


class LoaderRace(BaseModel):
    """Una razza (`races/<id>.yaml`)."""

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
    class_max_level: dict[str, int] = {}
    body: Optional[RaceBody] = None
    default_language: str = "common"
    class_skills: dict[str, dict[str, int]] = {}
    order: Optional[int] = None
    class_choices: list[list[str]] = []
    stat_modifiers: dict[str, int] = {}
    start_hp_bonus: int = 0
    move_modifier: int = 0


class ClassTitle(BaseModel):
    """Titolo di un livello: maschile e femminile."""

    male: str
    female: str


class HpGain(BaseModel):
    """Punti ferita guadagnati a ogni livello."""

    dice: tuple[int, int]
    until_level: int
    flat_after: int
    con_bonus_cap: Optional[int] = None


class LevelLoss(BaseModel):
    """Punti ferita persi scendendo di livello."""

    below: int
    low: int
    high: int
    minimum: int


class ClassMana(BaseModel):
    """Mana per classe."""

    base: int = 0
    per_level: int = 0
    level_divisor: int = 1
    only_class_cap: Optional[int] = None


class StartHp(BaseModel):
    """Punti ferita di partenza."""

    dice: tuple[int, int]
    bonus: int = 0
    group: Optional[str] = None


class LoaderClass(BaseModel):
    """Una classe (`classes/<id>.yaml`)."""

    class_id: str = ""
    disabled: Optional[bool] = False
    index: Optional[int] = None
    abbreviation: str = ""
    name: str = ""
    description: str = ""
    attrs_priority: list[str] = []
    exp_per_level: list[int] = []
    titles: list[ClassTitle] = []
    thac0: list[int] = []
    hp_gain: Optional[HpGain] = None
    level_loss: Optional[LevelLoss] = None
    start_hp: Optional[StartHp] = None
    mana: Optional[ClassMana] = None
    magic_order: Optional[int] = None
    pure_move_bonus: int = 0
    variant: Optional[str] = None
    start_alignment: Optional[int] = None
    saving_throws: dict[str, list[int]] = {}


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


def _layers(definitions: "Path | tuple[Path, ...] | None") -> tuple[Path, ...]:
    """Una cartella o una serie di strati (il successivo sostituisce lo stesso id del precedente)."""
    if definitions is None:
        return ()
    return (definitions,) if isinstance(definitions, Path) else tuple(definitions)


def read_races(definitions: "Path | tuple[Path, ...] | None") -> dict[str, LoaderRace]:
    """Le razze caricabili, per `race_id` (strati in ordine: il gioco ha prima il suo pacchetto, poi `definitions_path`)."""
    found: dict[str, LoaderRace] = {}
    for layer in _layers(definitions):
        found.update(_read(layer / "races", LoaderRace, "race_id"))  # type: ignore[arg-type]
    return found


def read_classes(definitions: "Path | tuple[Path, ...] | None") -> dict[str, LoaderClass]:
    """Le classi caricabili (non `disabled`), per `class_id`, con gli stessi strati delle razze."""
    found: dict[str, LoaderClass] = {}
    for layer in _layers(definitions):
        found.update(_read(layer / "classes", LoaderClass, "class_id"))  # type: ignore[arg-type]
    return {key: value for key, value in found.items() if not value.disabled}
