from __future__ import annotations

from pydantic import Field

from shared.config import Settings


class ETLSettings(Settings):
    """Extended settings for the ETL / pipeline service (extractor credentials)."""

    # Sync
    sync_interval_seconds: int = 300

    # --- Extractor credentials ---

    # Slack
    pov_slack_token: str = Field(default="", alias="POV_SLACK_TOKEN")
    pov_slack_user_token: str = Field(default="", alias="POV_SLACK_USER_TOKEN")

    # Linear
    pov_linear_api_key: str = Field(default="", alias="POV_LINEAR_API_KEY")

    # GitHub
    pov_github_token: str = Field(default="", alias="POV_GITHUB_TOKEN")

    # Google (OAuth2)
    pov_google_client_id: str = Field(default="", alias="POV_GOOGLE_CLIENT_ID")
    pov_google_client_secret: str = Field(default="", alias="POV_GOOGLE_CLIENT_SECRET")
    pov_google_refresh_token: str = Field(default="", alias="POV_GOOGLE_REFRESH_TOKEN")

    # Google (service account)
    pov_google_service_account_key: str = Field(default="", alias="POV_GOOGLE_SERVICE_ACCOUNT_KEY")

    # Granola
    pov_granola_access_token: str = Field(default="", alias="POV_GRANOLA_ACCESS_TOKEN")
    pov_granola_access_token_2: str = Field(default="", alias="POV_GRANOLA_ACCESS_TOKEN_2")
    pov_granola_enterprise_api_key: str = Field(default="", alias="POV_GRANOLA_ENTERPRISE_API_KEY")

    # Attio
    pov_attio_api_key: str = Field(default="", alias="POV_ATTIO_API_KEY")

    # Pylon
    pov_pylon_api_token: str = Field(default="", alias="POV_PYLON_API_TOKEN")

    # BetterStack
    pov_betterstack_api_token: str = Field(default="", alias="POV_BETTERSTACK_API_TOKEN")
