"""Bacheche e posta del gioco, in sola lettura. Prefisso `/api/content`.

Le bacheche sono gli oggetti BOARD dei YAML (`board_id`, o il vnum se manca, come fa il gioco) piu' i `board_id` che hanno messaggi nel
DB (`board_message`) anche senza oggetto. La posta e' solo un conteggio per destinatario: il testo delle lettere non si legge mai.
Le tabelle sono opzionali (`schema.OPTIONAL_TABLES`): se mancano la risposta lo dice, senza errore.

La moderazione (cancellare un messaggio, svuotare una bacheca) NON e' qui: il gioco tiene i messaggi in una copia in memoria
(`BoardStore`) e la posizione nella lista e' il numero con cui si leggono, quindi una DELETE sul DB la lascerebbe stantia: si passa dal
canale live (`board.delete` / `board.clear`, vedi `worldlive`).
"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from pachifast.database import AliasedBaseModel
from pachifast.router_factory import get_router
from sqlalchemy import func, select

from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, SessionDep
from pachimudeditor_adapter_pachimud.schema import models_of

router = get_router(name="content", deps=[Depends(require_capability("supports_boards"))])


class BoardObject(AliasedBaseModel):
    """Un oggetto BOARD che usa la bacheca."""

    vnum: int
    name: str
    zone_id: int
    zone_name: str


class BoardItem(AliasedBaseModel):
    """Una bacheca: il suo `board_id`, gli oggetti che la usano e quanti messaggi ha."""

    board_id: str
    count: int
    objects: list[BoardObject]
    max_messages: int | None
    """Limite dei messaggi (dal primo oggetto), `None` se non ha oggetti."""
    orphan: bool
    """Ha messaggi nel DB ma nessun oggetto BOARD la usa."""


class BoardsOut(AliasedBaseModel):
    """Elenco delle bacheche e disponibilita' delle tabelle del DB."""

    board_table: bool
    mail_table: bool
    boards: list[BoardItem]


class BoardMessageOut(AliasedBaseModel):
    """Un messaggio di bacheca; `number` e' la posizione (da 1) con cui lo legge il gioco."""

    id: int
    number: int
    author: str
    title: str
    text: str
    created_at: datetime


class MailCount(AliasedBaseModel):
    """Lettere in attesa di un destinatario (solo il conteggio)."""

    recipient: str
    count: int


class MailOut(AliasedBaseModel):
    """Posta in attesa per destinatario, senza testi."""

    available: bool
    total: int
    recipients: list[MailCount]


@router.get("/boards", response_model=BoardsOut)
async def list_boards(adapter: PachimudDep, session: SessionDep) -> BoardsOut:
    """Le bacheche (oggetti BOARD e `board_id` presenti nel DB) con il conteggio dei messaggi."""
    tables = models_of(session).tables
    counts: dict[str, int] = {}
    if (table := tables.get("board_message")) is not None:
        rows = await session.execute(select(table.c.board_id, func.count(table.c.id)).group_by(table.c.board_id))
        counts = {board_id: count for board_id, count in rows.all()}
    objects: dict[str, list[BoardObject]] = {}
    limits: dict[str, int] = {}
    for item in adapter.sync().all_items("object"):
        if getattr(item.model, "object_type", None) != "BOARD":
            continue
        board_id = item.model.board_id or str(item.vnum)
        objects.setdefault(board_id, []).append(
            BoardObject(vnum=item.vnum, name=item.model.short_description, zone_id=item.zone.vnum, zone_name=item.zone.model.name)
        )
        limits.setdefault(board_id, item.model.max_messages)
    boards = [
        BoardItem(
            board_id=board_id,
            count=counts.get(board_id, 0),
            objects=objects.get(board_id, []),
            max_messages=limits.get(board_id),
            orphan=board_id not in objects,
        )
        for board_id in sorted(set(objects) | set(counts))
    ]
    return BoardsOut(board_table="board_message" in tables, mail_table="mail_message" in tables, boards=boards)


@router.get("/boards/{board_id}/messages", response_model=list[BoardMessageOut])
async def list_board_messages(board_id: str, session: SessionDep, search: Annotated[str | None, Query()] = None) -> list[BoardMessageOut]:
    """I messaggi di una bacheca dal piu' vecchio; `search` filtra per autore, titolo o testo (il numero resta quello del gioco)."""
    table = models_of(session).tables.get("board_message")
    if table is None:
        return []
    rows = (await session.execute(select(table).where(table.c.board_id == board_id).order_by(table.c.id))).all()
    needle = (search or "").strip().lower()
    return [
        BoardMessageOut(id=row.id, number=number, author=row.author, title=row.title, text=row.text, created_at=row.created_at)
        for number, row in enumerate(rows, 1)
        if not needle or needle in f"{row.author}\n{row.title}\n{row.text}".lower()
    ]


@router.get("/mail", response_model=MailOut)
async def mail_counts(session: SessionDep) -> MailOut:
    """Quante lettere aspettano ogni destinatario. Il testo delle lettere non viene mai letto (scelta di privacy)."""
    table = models_of(session).tables.get("mail_message")
    if table is None:
        return MailOut(available=False, total=0, recipients=[])
    rows = (await session.execute(select(table.c.recipient, func.count(table.c.id)).group_by(table.c.recipient))).all()
    recipients = sorted((MailCount(recipient=name, count=count) for name, count in rows), key=lambda r: r.recipient)
    return MailOut(available=True, total=sum(r.count for r in recipients), recipients=recipients)
