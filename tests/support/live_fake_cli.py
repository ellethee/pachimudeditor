"""Avvia il finto server `livectl` su un socket e resta in esecuzione (stack E2E).

Uso: python -m tests.support.live_fake_cli <socket> <token> [dikumod|pachimud]   (cwd = radice del repo)
I giocatori connessi corrispondono a quelli SINTETICI dei file (`tests/support/dikumod_players.py`): Tizio in gioco (con l'inventario di prova di Tester), Caio col link caduto.
Scrive `ready` su stdout quando il socket e' pronto.
"""

import asyncio
import copy
import sys

from tests.support.live_fake_server import FakeLiveServer, FakePachimudServer


async def main(path: str, token: str, profile: str = "dikumod") -> None:
    """Apre il socket con Tizio (in gioco, guerriero 12) e Caio (link morto) e aspetta di essere terminato."""
    if profile == "pachimud":  # profilo del gioco pachimud: Tester (stanza 1001) e Ghost, vedi `FakePachimudServer`
        server = FakePachimudServer(path, token)
        await server.start()
        print("ready", flush=True)
        await asyncio.Event().wait()
        return
    server = FakeLiveServer(path, token)
    server.players["tizio"] = FakeLiveServer._new_player("Tizio", {"warrior": 12}, "playing")  # noqa: SLF001
    server.players["caio"] = FakeLiveServer._new_player("Caio", {"warrior": 20, "thief": 31}, "linkdead")  # noqa: SLF001
    for key in (
        "equipment",
        "carrying",
        "carry_weight",
    ):  # stesso inventario di prova di Tester (giubbotto, borsa con bottiglia, bottiglia)
        server.players["tizio"][key] = copy.deepcopy(server.players["tester"][key])
    del server.players["tester"], server.players["ghost"]
    await server.start()
    print("ready", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
