"""Error text that is safe to put on the public internet.

Two rules, and they pull against each other:

* An operator needs to know what broke. "Something went wrong" wastes the one
  chance the message has to be useful.
* A public deployment must not narrate its own filesystem. Absolute paths name
  the image layout, the user the process runs as, and often the repository the
  code came from -- none of which is the browser's business.

So: the message survives, the paths do not, and anything genuinely unexpected
becomes an opaque 500 carrying an id that ties the response to one line in the
server log.
"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

#: Any absolute POSIX or Windows path, however it is quoted.
_PATH = re.compile(r"(?:[A-Za-z]:)?(?:/[^\s'\"<>|]+){2,}|[A-Za-z]:\\[^\s'\"<>|]+")
_MAX_DETAIL = 300


def public_detail(exc: BaseException | str) -> str:
    """The exception's message with filesystem paths removed and length capped."""
    if isinstance(exc, str):
        text = exc
    elif isinstance(exc, KeyError):
        # str(KeyError("x")) is "'x'" -- the repr of the key, quotes and all.
        # Those quotes end up doubled once the detail is JSON-encoded.
        text = exc.args[0] if exc.args and isinstance(exc.args[0], str) else f"{exc}"
    else:
        text = f"{exc}"
    text = _PATH.sub("<path>", text).strip()
    if len(text) > _MAX_DETAIL:
        text = text[: _MAX_DETAIL - 1].rstrip() + "…"
    return text or "unavailable"


async def key_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A missing site, facility or scenario is a 404, not a server failure."""
    return JSONResponse(status_code=404, content={"detail": public_detail(exc)})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything unexpected: logged in full, disclosed as an id.

    The traceback goes to the log, where the person who can act on it will
    look. The client gets a 500 and a reference, because a stack trace in a
    browser is a map of the server for anyone who asks for one.
    """
    reference = uuid.uuid4().hex[:12]
    log.exception("unhandled error [%s] on %s %s", reference, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "The server could not complete this request.",
            "reference": reference,
        },
    )
