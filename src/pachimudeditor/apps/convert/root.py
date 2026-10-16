"""Conversione di zone tra mondi diversi (es. BasedMud -> pachimud). Prefisso `/api/convert`.

I mondi si scelgono per id nel corpo (non con `X-World`): sorgente e arrivo sono due mondi insieme.
"""

from pachifast.router_factory import get_router

from pachimudeditor.apps.convert import service
from pachimudeditor.apps.convert.schemas import ConvertRequest, PairsResponse
from pachimudeditor.common.adapters.convert.models import ConvertReport

router = get_router()


@router.get("/pairs", response_model=PairsResponse)
async def pairs() -> PairsResponse:
    """Mondi configurati e coppie (sorgente, arrivo) con tipo di convertitore e ammissibilita'."""
    return service.list_pairs()


@router.post("/preview", response_model=ConvertReport)
async def preview(body: ConvertRequest) -> ConvertReport:
    """Anteprima: cosa si creerebbe/sostituirebbe, tabella dei vnum, perdite e conflitti. Non scrive nulla."""
    return await service.run_conversion(body, force_dry_run=True)


@router.post("/run", response_model=ConvertReport)
async def run(body: ConvertRequest) -> ConvertReport:
    """Conversione. Scrive solo con `dryRun=false` **e** `confirm=true` (altrimenti dry-run o 422
    `convert.confirm_required`); con un errore a meta' annulla quanto creato (`rolledBack`)."""
    return await service.run_conversion(body, force_dry_run=False)
