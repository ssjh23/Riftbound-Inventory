import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = Path(os.environ.get("RIFTBOUND_DATA_DIR", BACKEND_DIR / "data"))
    (d / "images").mkdir(parents=True, exist_ok=True)
    return d


def jwt_secret() -> str:
    if val := os.environ.get("RIFTBOUND_JWT_SECRET"):
        return val
    key_file = data_dir() / "secret.key"
    if key_file.exists():
        return key_file.read_text().strip()
    secret = secrets.token_hex(32)
    key_file.write_text(secret)
    return secret


TOKEN_EXPIRE_DAYS = int(os.environ.get("RIFTBOUND_TOKEN_EXPIRE_DAYS", "30"))


def cors_origins() -> list[str]:
    raw = os.environ.get(
        "RIFTBOUND_CORS_ORIGINS",
        "http://localhost:5173,https://localhost:5173",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


# --- Pricing (market price / trend feature) --------------------------------
# API key for the external price source (riftbound-api.com / TCGGO, via
# RapidAPI). Not committed anywhere — set as an environment variable (or an
# Infisical secret). Pricing endpoints report "not configured" and the rest
# of the app works normally when this is unset.
def price_api_key() -> str | None:
    return os.environ.get("RIFTBOUND_PRICE_API_KEY") or None


def topdeck_api_key() -> str | None:
    return os.environ.get("RIFTBOUND_TOPDECK_KEY") or None


def price_api_host() -> str:
    return os.environ.get(
        "RIFTBOUND_PRICE_API_HOST", "riftbound-prices-api.p.rapidapi.com"
    )


# Free tier is 100 requests/day; stay under it with margin for other traffic.
PRICE_DAILY_BUDGET = int(os.environ.get("RIFTBOUND_PRICE_DAILY_BUDGET", "90"))
# A cached price older than this triggers an on-demand refresh (budget permitting).
PRICE_STALE_HOURS = int(os.environ.get("RIFTBOUND_PRICE_STALE_HOURS", "24"))
