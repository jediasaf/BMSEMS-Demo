"""Turning a requested identifier into the one the dataset actually uses.

The published dataset numbers its sites, so every adapter ends up casting the
requested id to an int. Done inline, that cast turns "a site that does not
exist" into ``ValueError: invalid literal for int()`` -- which is a 500 and a
stack trace, for a request whose only fault is naming something absent.

``as_numeric_id`` makes the missing thing a ``KeyError``, which is what the
rest of the stack already treats as "not found".
"""

from __future__ import annotations


def as_numeric_id(asset_id: str | int, *, kind: str = "asset") -> int:
    """The dataset's integer id, or KeyError if this is not one of them."""
    try:
        return int(asset_id)
    except (TypeError, ValueError) as exc:
        raise KeyError(f"unknown {kind} {asset_id!r}") from exc
