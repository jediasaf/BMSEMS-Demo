"""Timestamp normalisation at the API boundary.

The source publishes timestamps with no UTC offset, so the whole platform works
in the dataset's own local clock. A client that serialises an instant as UTC
(``...Z``) would otherwise reach pandas as a tz-aware value and blow up on the
first comparison with the tz-naive index.

The offset is *dropped*, not converted: converting would silently shift the
replay cursor by the client's timezone, which is a worse failure than an error
because it looks like it worked.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def naive_instant(value: datetime | str | None) -> pd.Timestamp | None:
    """Coerce an incoming instant to a tz-naive ``pd.Timestamp``."""
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp
