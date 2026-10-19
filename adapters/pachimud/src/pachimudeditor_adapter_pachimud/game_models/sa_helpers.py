# Copia di pachimud/database/sa_helpers.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

"""Small SQLAlchemy column-construction helpers shared across models.

These exist because plain type inference does not give us what the
schema needs on its own:

- SQLAlchemy's own `Enum` type is fundamentally a *string* type: it
  computes its `VARCHAR` length from `len()` of each member's value,
  so it flat out cannot back an `IntEnum` (crashes on construction).
  There is no "native int enum" column type in SQLAlchemy — storing
  an `IntEnum` as a real `SMALLINT` needs a small `TypeDecorator`.
- A field typed as a plain `list`/`dict` gets no column type at all
  without an explicit `JSON` column.

`int_enum_column` wraps that `TypeDecorator` once so every int-enum
column in the schema is a genuine `SMALLINT` (small storage, fast
indexing) while still reading back as a real enum member in Python
(`isinstance(row.sex, Sex)`, `row.sex.name`, ...), not a bare int.
"""

from enum import IntEnum
from typing import Any, TypeVar

import sqlalchemy as sa
from sqlalchemy.orm import MappedColumn, mapped_column

E = TypeVar("E", bound=IntEnum)


def _int_enum_type(enum_cls: type[E]) -> sa.types.TypeDecorator:
    """Build a `TypeDecorator` storing `enum_cls` as a `SMALLINT`.

    Writes `int(member)`, reads back `enum_cls(value)` — so the column
    is a plain, indexable integer on disk, but a real `enum_cls`
    instance in Python once loaded.
    """

    class _IntEnumType(sa.types.TypeDecorator):
        impl = sa.SmallInteger
        cache_ok = True

        def process_bind_param(self, value: E | int | None, dialect: Any) -> int | None:
            return None if value is None else int(value)

        def process_result_value(self, value: int | None, dialect: Any) -> E | None:
            return None if value is None else enum_cls(value)

    return _IntEnumType()


def int_enum_column(enum_cls: type[E], /, **column_kwargs: Any) -> MappedColumn:
    """Build a `Column` for an `IntEnum`, stored as a real `SMALLINT`."""
    return mapped_column(_int_enum_type(enum_cls), **column_kwargs)


def json_str_list_column(**column_kwargs: Any) -> MappedColumn:
    """Build a `Column` for a `list[str]` stored as JSON.

    Used for flag sets (room/mob flags, object extra/wear flags).
    Flags are read/interpreted in application code after a record is
    loaded, not filtered on in SQL, so a JSON column is a pragmatic
    choice here over a fully normalized flag-per-row join table; JSON
    is natively supported by both SQLite and PostgreSQL, so this
    stays portable if the project later moves to PostgreSQL.
    """
    return mapped_column(sa.JSON, **column_kwargs)


def json_int_list_column(**column_kwargs: Any) -> MappedColumn:
    """Build a `Column` for a `list[int]` stored as JSON.

    Used for `House.guest_ids` — a handful of character ids per house,
    same pragmatic reasoning as `json_str_list_column`: read/checked
    in application code after a record is loaded, not filtered on in
    SQL, so JSON beats a normalized per-guest join table here.
    """
    return mapped_column(sa.JSON, **column_kwargs)


def json_int_dict_column(**column_kwargs: Any) -> MappedColumn:
    """Build a `Column` for a `dict[str, int]` stored as JSON.

    Used for per-character skill success percentages
    (`PlayerCharacter.skill_percentages`). Same pragmatic reasoning as
    `json_str_list_column`: read/interpreted in application code after
    a record is loaded, not filtered on in SQL, so a JSON column beats
    a fully normalized per-skill join table here, and stays portable
    to PostgreSQL later.
    """
    return mapped_column(sa.JSON, **column_kwargs)
