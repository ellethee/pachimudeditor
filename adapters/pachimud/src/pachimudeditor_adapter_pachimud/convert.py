"""Sapore pachimud: il pivot *e'* il modello di pachimud, quindi quasi tutto e' l'identita'.

Verso pachimud (`from_pivot`) restano due cose: la razza deve essere una di quelle di `definitions/races` (altrimenti
`raceId` diventa `None` con un avviso) e i flag sono in minuscolo come in ROM.
"""

from pachimudeditor.common.adapters.convert.helpers import norm_race, pick_race
from pachimudeditor.sdk import Flavor
from pachimudeditor.sdk import ConvertContext, Converted
from pachimudeditor.common.adapters.models import MobIn


class PachimudFlavor(Flavor):
    """Mondo pachimud (database SQLAlchemy). Non ha `extra`: i DTO di arrivo devono averlo vuoto."""

    kind = "pachimud"
    door_state_in_resets = False

    def mob_from_pivot(self, m: MobIn, ctx: ConvertContext) -> Converted[MobIn]:
        """Valida la razza contro quelle del mondo (pachimud: id = nome del file YAML)."""
        race = norm_race(m.race_id)
        picked, losses = pick_race(race, [race] if race else [], ctx)
        return Converted(m.model_copy(update={"race_id": picked, "extra": {}}), losses)
