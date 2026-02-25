from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_REPOS: list[str] = [
    "tempoxyz/tempo",
    "tempoxyz/ai",
    "tempoxyz/ai_v2",
    "tempoxyz/metronome",
    "tempoxyz/tempo-apps",
    "tempoxyz/tempo-web",
    "tempoxyz/app",
    "tempoxyz/docs",
    "tempoxyz/tempo-ts",
    "tempoxyz/tempo-go",
    "tempoxyz/tempo-foundry",
    "tempoxyz/tempo-std",
    "tempoxyz/ai-payments",
    "tempoxyz/dev-infra",
    "tempoxyz/prd-infra",
    "tempoxyz/helm-charts",
    "tempoxyz/ci",
    "tempoxyz/mpp",
    "tempoxyz/mpp-rs",
    "tempoxyz/presto",
    "tempoxyz/presto-rs",
    "tempoxyz/agent-skills",
    "tempoxyz/derek",
    "tempoxyz/profiler-cli",
    "tempoxyz/dev-portal",
    "tempoxyz/tempo-stack",
    "tempoxyz/chains",
    "tempoxyz/lints",
]


class RepoSpec(BaseModel):
    """Specification for a repository to include in the sandbox."""

    full_name: str = Field(description="org/name, e.g. 'tempoxyz/tempo'")
    branch: str = Field(default="main", description="Branch to clone")
    shallow: bool = Field(default=True, description="Use shallow clone (--depth=1)")

    @property
    def org(self) -> str:
        return self.full_name.split("/")[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/")[1]

    @property
    def clone_url(self, token: str | None = None) -> str:
        if token:
            return f"https://{token}@github.com/{self.full_name}.git"
        return f"https://github.com/{self.full_name}.git"

    def get_clone_url(self, token: str | None = None) -> str:
        if token:
            return f"https://{token}@github.com/{self.full_name}.git"
        return f"https://github.com/{self.full_name}.git"


class SandboxConfig(BaseSettings):
    """Configuration for the sandbox builder."""

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    github_token: str = Field(
        default="",
        description="GitHub token for cloning private repos",
    )
    repos: list[str] = Field(
        default_factory=lambda: list(DEFAULT_REPOS),
        description="List of repos to include (org/name format)",
    )
    sandbox_image_name: str = Field(
        default="tempo-ai-sandbox",
        description="Docker image name for the sandbox",
    )
    update_interval_hours: int = Field(
        default=6,
        description="Hours between automatic repo syncs",
    )
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="URL for connecting sandbox to the API layer",
    )

    def get_repo_specs(self) -> list[RepoSpec]:
        """Convert repo strings to RepoSpec objects."""
        return [RepoSpec(full_name=r) for r in self.repos]
