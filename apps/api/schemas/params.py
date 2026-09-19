"""Bounded query parameters.

Every identifier this API accepts comes from a closed set the server already
knows: a site id, a facility id, a scenario id, a recommendation id. None of
them is free text, so none of them should be accepted as free text.

Declaring the bound here rather than in each signature means FastAPI rejects a
1 MB "site_id" with a 422 before any handler, adapter or DataFrame sees it, and
the constraint is visible in the OpenAPI schema instead of implied by whatever
the lookup happens to do with a bad value.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query

#: Identifiers are alphanumeric with the separators the project actually uses.
#: Notably absent: path separators, quotes, whitespace and percent signs.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"
ID_MAX_LENGTH = 64

AssetId = Annotated[
    str | None,
    Query(max_length=ID_MAX_LENGTH, pattern=ID_PATTERN),
]
ScenarioId = Annotated[
    str,
    Query(max_length=ID_MAX_LENGTH, pattern=ID_PATTERN),
]
ModuleName = Annotated[
    str | None,
    Query(max_length=16, pattern=r"^(bms|ems|BMS|EMS)$"),
]
RecommendationId = Annotated[
    str,
    Path(max_length=ID_MAX_LENGTH, pattern=ID_PATTERN),
]
#: The Control Lab horizon. Four hours is the shortest run that shows thermal
#: mass doing anything; 48 is the longest the demo will wait for.
HorizonHours = Annotated[int, Query(ge=4, le=48)]
