"""Semina nel DB di gioco temporaneo un account con un personaggio (i personaggi non si creano dall'editor).

Uso: python <questo file> <cartella temporanea>   (cwd = radice del repo, come `tests.support.stack`)
"""

import sys
from pathlib import Path

import pachimudeditor_adapter_pachimud.game_models  # noqa: F401  registra i modelli
from pachimudeditor_adapter_pachimud.game_models.account import Account
from pachimudeditor_adapter_pachimud.security import hash_password
from pachimudeditor_adapter_pachimud.game_models.enums import Sex
from pachimudeditor_adapter_pachimud.game_models.character import PlayerCharacter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main(workdir: Path) -> None:
    """Crea l'account `seed-account` e il personaggio `Seedhero`."""
    engine = create_engine(f"sqlite:///{workdir / 'game.db'}")
    with Session(engine) as s:
        account = Account(username="seed-account", password_hash=hash_password("Password-di-test-123"), email=None)
        s.add(account)
        s.flush()
        s.add(PlayerCharacter(
            account_id=account.id, name="Seedhero", level=5, experience=0, hit_points_current=30, hit_points_max=30,
            gold=10, sex=Sex.NEUTRAL, class_id="warrior", race_id="human", strength=12, dexterity=12,
            constitution=12, intelligence=12, wisdom=12, charisma=12, mana_current=10, mana_max=10,
        ))
        s.commit()
    engine.dispose()


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
