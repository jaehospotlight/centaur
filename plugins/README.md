# Plugins

Drop plugin directories here. Each plugin needs:

```
plugins/
  my-plugin/
    pyproject.toml   # [tool.ai-v2-plugin] section with module path
    .env.example     # Document required secrets
    src/ai_v2_plugin_my_plugin/
      __init__.py
      client.py      # API client class + _client() factory
      cli.py         # typer CLI for standalone use
```

## Writing a plugin

```python
# client.py
from ai_v2.plugin_sdk import secret


class MyClient:
    def search(self, query: str, limit: int = 10) -> dict:
        """Search something."""
        token = secret("MY_API_TOKEN")
        # ... use token, return results ...
        return {"results": [...]}


def _client() -> MyClient:
    return MyClient()
```

## Secrets

Secrets are resolved in this order:
1. **Plugin `.env`** — per-plugin overrides in `plugins/<name>/.env`
2. **Root `.env`** — central file at repo root (define all secrets here)
3. **Environment variables** — for Docker, k8s, sops, 1Password, etc.

Use `secret("KEY")` to access. Never use `os.environ` — plugin secrets are scoped.

## Available Plugins

| Plugin | Description | Secrets |
|--------|-------------|---------|
| slack | Slack messages, channels, threads | SLACK_BOT_TOKEN |
| linear | Linear issues, projects, cycles | LINEAR_API_KEY |
| gsuite | Gmail, Calendar, Drive | GOOGLE_CREDENTIALS_JSON, GOOGLE_TOKEN_JSON |
| notion | Notion pages, databases | NOTION_API_KEY |
| paradigmdb | Internal PostgreSQL, Shift notes, BigQuery | RESHIFT_DB_*, GCP auth |
| figma | Figma design system extraction | FIGMA |
| allium | On-chain analytics, SQL | ALLIUM_API_KEY |
| coingecko | Crypto market data | COINGECKO_API_KEY |
| coinmetrics | Crypto market & on-chain analytics | COINMETRICS_API_KEY |
| defillama | DeFi & stablecoin analytics | (none — public API) |
| dune | Dune Analytics queries | DUNE_API_KEY |
| messari | Crypto asset research | MESSARI_API_KEY |
| nansen | Blockchain analytics, wallet labels | NANSEN_API_KEY |
| posthog | Product analytics, HogQL | POSTHOG_API_KEY, POSTHOG_PROJECT_ID |
| similarweb | Web traffic intelligence | SIMILARWEB_API_KEY |
| kalshi | Prediction markets | KALSHI_API_KEY |
| polymarket | Prediction markets | (none — public API) |
| falconx | OTC crypto trading | FALCONX_API_KEY, FALCONX_API_SECRET, FALCONX_PASSPHRASE |
| coinbase | Coinbase Prime custody | COINBASE_API_KEY, COINBASE_API_SECRET, COINBASE_PASSPHRASE |
| anchorage | Anchorage Digital custody | ANCHORAGE_API_KEY, ANCHORAGE_API_SECRET |
| bitgo | BitGo wallet management | BITGO_ACCESS_TOKEN, BITGO_ENTERPRISE_ID |

## Profiles

Set `ACTIVE_PROFILE=research` to only load plugins listed in `profiles/research.json`:

```json
{"plugins": ["slack", "linear", "gsuite"]}
```

If not set, all discovered plugins are loaded.
