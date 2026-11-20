"""Bacheche e posta pachimud (sola lettura): `/api/content/boards`, `/boards/{id}/messages`, `/mail`."""

from datetime import UTC, datetime, timedelta

import httpx

from tests.helpers import data


async def _seed() -> None:
    """Messaggi di due bacheche (una senza oggetto) e lettere di due destinatari, come li scriverebbe il gioco."""
    from pachimudeditor_adapter_pachimud.game_models.messages import BoardMessage, MailMessage

    from tests.support.gamedb import get_session_factory

    now = datetime.now(UTC)
    async with get_session_factory()() as s:
        s.add_all(
            [
                BoardMessage(board_id="piazza", author="Aldo", title="Vendo spada", text="Una spada quasi nuova", created_at=now),
                BoardMessage(
                    board_id="piazza", author="Bea", title="Cerco gruppo", text="Per il drago", created_at=now + timedelta(seconds=1)
                ),
                BoardMessage(board_id="vecchia", author="Carlo", title="Ricordo", text="Bacheca senza oggetto", created_at=now),
                MailMessage(recipient="aldo", sender="Bea", text="SEGRETO"),
                MailMessage(recipient="aldo", sender="Carlo", text="SEGRETO"),
                MailMessage(recipient="bea", sender="Aldo", text="SEGRETO"),
            ]
        )
        await s.commit()


async def test_boards_messages_and_mail(client: httpx.AsyncClient) -> None:
    """Elenco con oggetti e orfane, messaggi numerati con ricerca, posta solo come conteggio (mai il testo)."""
    caps = data(await client.get("/api/worlds"))[0]["capabilities"]
    assert caps["supportsBoards"] is True
    zone = data(await client.get("/api/zones"))["items"][0]
    board = {"vnum": 1700, "zoneId": zone["id"], "keywords": "bacheca", "shortDescription": "la bacheca", "objectType": 24}
    assert data(await client.post("/api/objects", json=board), 201)["vnum"] == 1700
    await _seed()

    out = data(await client.get("/api/content/boards"))
    assert out["boardTable"] and out["mailTable"]
    by_id = {b["boardId"]: b for b in out["boards"]}
    # senza `board_id` il gioco usa il vnum come id; `piazza` e `vecchia` hanno solo messaggi
    assert by_id["1700"]["objects"][0]["vnum"] == 1700 and by_id["1700"]["count"] == 0 and not by_id["1700"]["orphan"]
    assert by_id["piazza"]["count"] == 2 and by_id["piazza"]["orphan"] and by_id["vecchia"]["orphan"]

    msgs = data(await client.get("/api/content/boards/piazza/messages"))
    assert [(m["number"], m["author"]) for m in msgs] == [(1, "Aldo"), (2, "Bea")]
    found = data(await client.get("/api/content/boards/piazza/messages", params={"search": "DRAGO"}))
    assert [(m["number"], m["title"]) for m in found] == [(2, "Cerco gruppo")]  # il numero resta quello del gioco
    assert data(await client.get("/api/content/boards/nessuna/messages")) == []

    mail = data(await client.get("/api/content/mail"))
    assert mail["available"] and mail["total"] == 3
    assert {r["recipient"]: r["count"] for r in mail["recipients"]} == {"aldo": 2, "bea": 1}
    assert "SEGRETO" not in (await client.get("/api/content/mail")).text
