"""Parte di sola lettura della suite di contratto, eseguita sulla copia dei dati REALI di dikumod e dikumod2."""

import pytest

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.models import RoomPageParams, ZonePageParams
from tests.adapter_contract.test_contract import test_describe_and_capabilities, test_meta  # noqa: F401  (riesportati)
from tests.dikumod.conftest import DikumodAdapter


@pytest.fixture
def adapter(ro: DikumodAdapter) -> WorldAdapter:
    """L'adapter di default (sola lettura) sui dati reali."""
    return ro


async def test_paging_and_search_on_real_data(adapter: WorldAdapter) -> None:
    """Paginazione, ricerca e ordinamento sui dati veri: pagine coerenti, vnum in ordine, ricerca per nome."""
    page = await adapter.list_zones(ZonePageParams(page=2, pageSize=10))
    assert len(page.items) == 10 and page.total == 93 and page.pages == 10
    rooms = (await adapter.list_rooms(RoomPageParams(page=1, pageSize=100))).items
    assert [r.vnum for r in rooms] == sorted(r.vnum for r in rooms)
    found = await adapter.list_rooms(RoomPageParams(search="Il vuoto"))
    assert found.total >= 1 and all("il vuoto" in r.name.lower() or "il vuoto" in str(r.vnum) for r in found.items)
    desc = await adapter.list_rooms(RoomPageParams(page=1, pageSize=5, orderBy="-vnum"))
    assert [r.vnum for r in desc.items] == sorted((r.vnum for r in desc.items), reverse=True)
