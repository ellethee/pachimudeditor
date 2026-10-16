"""Classi base degli schemi di richiesta condivise dalle app dell'editor."""

from typing import ClassVar

from pachifast.database import AliasedBaseModel
from pydantic import model_validator


class PatchModel(AliasedBaseModel):
    """Base dei body di aggiornamento parziale (PUT): un `null` esplicito su una colonna NOT NULL e' 422.

    Con `exclude_unset` un campo inviato a `null` verrebbe scritto cosi' com'e' e il DB risponderebbe con
    un 409 generico: qui lo si intercetta in validazione. Le sottoclassi elencano in `nullable_fields` i
    (soli) campi che ammettono davvero `null`, per nome Python.
    """

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _no_null_on_required(self) -> "PatchModel":
        """Rifiuta i campi esplicitamente inviati a `null` che non sono in `nullable_fields`."""
        for name in self.model_fields_set:
            if name not in self.nullable_fields and getattr(self, name) is None:
                raise ValueError(f"Il campo «{name}» non può essere null.")
        return self
