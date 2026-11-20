"""Sapore pachimud: il pivot *e'* il modello di pachimud, quindi quasi tutto e' l'identita'.

Verso pachimud (`from_pivot`) restano tre cose: la razza deve essere una di quelle di `definitions/races` (altrimenti
`raceId` diventa `None` con un avviso), i flag sono in minuscolo come in ROM e il reset `R` (rimescola le uscite), che il
gioco non ha, e' scartato con una perdita riportata.
"""

from pachimudeditor.common.adapters.convert.helpers import norm_race, pick_race
from pachimudeditor.sdk import Flavor
from pachimudeditor.sdk import ConvertContext, Converted
from pachimudeditor.common.adapters.models import MobIn, ResetCommandIn
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.sdk import loss


class PachimudFlavor(Flavor):
    """Mondo pachimud (file YAML). I suoi `extra` (area, statistiche dei mob, campi del tipo degli oggetti) non hanno equivalenti negli altri mondi."""

    kind = "pachimud"
    door_state_in_resets = False

    def reset_from_pivot(self, c: ResetCommandIn, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """`R` (rimescola le uscite) non esiste nel gioco: il comando e' scartato e riportato."""
        if c.command_type is ZoneCommandType.RANDOMIZE_EXITS:
            return Converted(None, [loss("reset", "command", "reset_unsupported_command", "dropped", letter="R")])
        return Converted(c)

    def mob_from_pivot(self, m: MobIn, ctx: ConvertContext) -> Converted[MobIn]:
        """Valida la razza contro quelle del mondo (pachimud: id = nome del file YAML)."""
        race = norm_race(m.race_id)
        picked, losses = pick_race(race, [race] if race else [], ctx)
        return Converted(m.model_copy(update={"race_id": picked, "extra": {}}), losses)
