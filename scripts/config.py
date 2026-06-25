import os
from pathlib import Path
from urllib.parse import urlencode


TOKEN_KEY_ENV_VAR = "IDX_TRESTLE_TOKEN_KEY"


def _read_dotenv_token_key() -> str | None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        if name.strip() == TOKEN_KEY_ENV_VAR:
            return value.strip().strip('"').strip("'")

    return None


def get_auth_endpoint() -> str:
    token_key = os.getenv(TOKEN_KEY_ENV_VAR) or _read_dotenv_token_key()

    if not token_key:
        raise SystemExit(
            f"Missing {TOKEN_KEY_ENV_VAR}. Add it to a private .env file or set it as an environment variable."
        )

    query = urlencode({"key": token_key})
    return f"https://idxexchange.com/internal-api/trestle_token.php?{query}"
