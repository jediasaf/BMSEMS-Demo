"""What the API does when the request is not the one the demo makes.

The happy path is covered elsewhere. These are the cases a public deployment
actually meets: a malformed identifier, an unknown scenario, an origin nobody
authorised, and a handler that raises. In each one the requirement is the
same -- a useful status code, a message the operator can act on, and nothing
about the server's filesystem or stack.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter

from apps.api.errors import public_detail

PRODUCTION_ORIGIN = "https://ecotwin-ai-zeta.vercel.app"
DEV_ORIGIN = "http://localhost:3000"
UNKNOWN_ORIGIN = "https://ecotwin-ai.attacker.example"


# -- bounded inputs --------------------------------------------------------
@pytest.mark.parametrize(
    "site_id",
    [
        "x" * 65,  # longer than any identifier this product has
        "../../etc/passwd",  # path traversal
        "227 OR 1=1",  # whitespace and operators
        "227%00",  # percent-encoded null
        "",  # empty
    ],
)
def test_a_malformed_site_id_is_rejected_before_any_handler(client, site_id: str) -> None:
    response = client.get("/bms/overview", params={"site_id": site_id})
    assert response.status_code == 422, response.text
    assert "site_id" in response.text


def test_a_malformed_scenario_id_is_rejected(client) -> None:
    assert client.get("/bms/overview", params={"scenario_id": "a" * 200}).status_code == 422


def test_the_control_lab_horizon_is_bounded(client) -> None:
    assert client.get("/bms/control-lab", params={"hours": 100000}).status_code == 422
    assert client.get("/bms/control-lab", params={"hours": 0}).status_code == 422


def test_a_well_formed_but_unknown_site_is_a_404_not_a_500(client) -> None:
    response = client.get("/bms/overview", params={"site_id": "no-such-site"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail == "unknown site 'no-such-site'"
    assert "Traceback" not in detail
    assert "/home/" not in detail and "/app/" not in detail


def test_an_unknown_scenario_is_a_404(client) -> None:
    response = client.get("/bms/overview", params={"scenario_id": "not_a_scenario"})
    assert response.status_code == 404


# -- what an error is allowed to say --------------------------------------
def test_absolute_paths_never_survive_into_a_message() -> None:
    detail = public_detail(
        FileNotFoundError("[Errno 2] No such file: '/home/user/BMSEMS-Demo/data/load.parquet'")
    )
    assert "/home/user" not in detail
    assert "<path>" in detail
    assert "No such file" in detail


def test_windows_paths_are_stripped_too() -> None:
    assert "C:\\" not in public_detail(r"cannot open C:\Users\ops\secrets\key.pem")


def test_a_long_message_is_capped() -> None:
    assert len(public_detail("x" * 5000)) <= 300


def test_an_empty_message_still_says_something() -> None:
    assert public_detail("") == "unavailable"


def test_a_key_error_is_not_double_quoted() -> None:
    """str(KeyError("x")) is "'x'"; JSON would then serve it as "\"'x'\""."""
    assert public_detail(KeyError("unknown site 'abc'")) == "unknown site 'abc'"


def test_an_unhandled_exception_returns_a_reference_not_a_traceback() -> None:
    """A handler that raises must not narrate the stack to the browser.

    ``raise_server_exceptions=False`` is what a real client sees: the test
    client's default is to re-raise, which is useful in development and is
    precisely the behaviour a public deployment must not have.
    """
    from fastapi.testclient import TestClient

    from apps.api.main import app

    router = APIRouter()

    @router.get("/_test/boom", include_in_schema=False)
    def boom() -> dict[str, str]:
        raise RuntimeError("secret detail from /srv/ecotwin/models/site-227.joblib")

    app.include_router(router)
    try:
        with TestClient(app, raise_server_exceptions=False) as raw_client:
            response = raw_client.get("/_test/boom")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "The server could not complete this request."
        assert len(body["reference"]) == 12
        assert "secret detail" not in response.text
        assert "joblib" not in response.text
        assert "Traceback" not in response.text
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "path", "") != "/_test/boom"
        ]


# -- CORS ------------------------------------------------------------------
def _preflight(client, origin: str):
    return client.options(
        "/bms/overview",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_the_production_frontend_origin_is_allowed(client) -> None:
    response = _preflight(client, PRODUCTION_ORIGIN)
    assert response.headers.get("access-control-allow-origin") == PRODUCTION_ORIGIN


def test_local_development_is_allowed(client) -> None:
    response = _preflight(client, DEV_ORIGIN)
    assert response.headers.get("access-control-allow-origin") == DEV_ORIGIN


def test_an_unknown_origin_gets_no_grant(client) -> None:
    """The allowlist is closed: an origin nobody configured is not answered."""
    response = _preflight(client, UNKNOWN_ORIGIN)
    assert response.headers.get("access-control-allow-origin") is None


def test_a_lookalike_origin_is_not_a_prefix_match(client) -> None:
    response = _preflight(client, PRODUCTION_ORIGIN + ".attacker.example")
    assert response.headers.get("access-control-allow-origin") is None


def test_credentials_are_never_granted(client) -> None:
    """No cookies, no auth headers -- so no credentialed cross-origin access."""
    response = client.get("/healthz", headers={"Origin": PRODUCTION_ORIGIN})
    assert response.headers.get("access-control-allow-credentials") is None


def test_the_configured_origin_list_contains_no_wildcard() -> None:
    from apps.api.config import get_settings

    origins = get_settings().cors_origin_list
    assert origins
    assert "*" not in origins
    assert all(o.startswith("http://") or o.startswith("https://") for o in origins)


# -- health endpoints ------------------------------------------------------
def test_healthz_is_liveness_only(client) -> None:
    """It must stay cheap enough to poll every few seconds forever."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # Nothing heavy: the body names no component, because it inspected none.
    assert "components" not in response.text


def test_health_reports_each_component(client) -> None:
    components = client.get("/health").json()["components"]
    assert set(components) >= {"api", "data", "models", "pandapower", "boptest"}


def test_health_notes_carry_no_filesystem_paths(client) -> None:
    for note in client.get("/health").json()["notes"]:
        assert "/home/" not in note and "/app/" not in note


# -- the reset endpoint ----------------------------------------------------
def test_a_second_reset_inside_the_cooldown_is_declined(client) -> None:
    """The reset is global and expensive; it is not a public loop."""
    from apps.api.routers import system

    system._last_reset = 0.0
    first = client.post("/demo/reset").json()
    assert first["reset"] is True
    second = client.post("/demo/reset").json()
    assert second["reset"] is False
    assert "client-side" in second["note"]
    system._last_reset = 0.0
