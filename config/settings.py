import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"ERROR: Required env var '{key}' is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# Anthropic
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = _optional("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Spend limits
DAILY_SPEND_LIMIT_USD: float = float(_optional("DAILY_SPEND_LIMIT_USD", "5.00"))

# Adzuna
ADZUNA_APP_ID: str = _optional("ADZUNA_APP_ID")
ADZUNA_APP_KEY: str = _optional("ADZUNA_APP_KEY")

# GitHub (optional — unauthenticated rate limit is 60/hr, authenticated is 5000/hr)
GITHUB_TOKEN: str = _optional("GITHUB_TOKEN")

# Paths
SPEND_LEDGER_PATH: str = _optional("SPEND_LEDGER_PATH", "data/spend_ledger.json")

# Spend alert email (all optional — alerts disabled if ALERT_EMAIL not set)
ALERT_EMAIL: str = _optional("ALERT_EMAIL")          # address to notify
SMTP_HOST: str = _optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(_optional("SMTP_PORT", "587"))
SMTP_USER: str = _optional("SMTP_USER")              # sender Gmail address
SMTP_PASSWORD: str = _optional("SMTP_PASSWORD")      # Gmail app password
