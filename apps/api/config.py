"""Runtime configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECOTWIN_", env_file=".env", extra="ignore")

    app_name: str = "EcoTwin AI"
    version: str = "1.0.0"
    #: Public demo mode: prefer precomputed results and never start a long job.
    demo_mode: bool = True
    #: Interview mode: curated data, stable scenarios, no experimental surface.
    interview_mode: bool = True
    #: Base URL of a BOPTEST REST instance. Empty disables live BOPTEST.
    boptest_url: str = ""
    #: Allowed CORS origins, comma-separated. Deliberately a closed list: the
    #: two production frontend aliases plus local development. An empty list
    #: means no cross-origin browser access at all, which is the right answer
    #: for a misconfigured deployment -- "*" is not.
    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://ecotwin-ai-zeta.vercel.app,"
        "https://ecotwin-ai-jediasafs-projects.vercel.app"
    )
    #: Serve simulation results from the demo cache when one exists.
    use_demo_cache: bool = True
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
