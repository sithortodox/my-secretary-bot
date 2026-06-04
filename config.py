import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Validate critical environment variables
def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"❌ ERROR: Required environment variable {name} is not set!", file=sys.stderr)
        print(f"   Please set it in .env file or environment.", file=sys.stderr)
        sys.exit(1)
    return value

def _require_int(name: str) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"❌ ERROR: Required environment variable {name} is not set!", file=sys.stderr)
        sys.exit(1)
    try:
        return int(value)
    except ValueError:
        print(f"❌ ERROR: Environment variable {name} must be an integer!", file=sys.stderr)
        sys.exit(1)

# Critical - must be set
BOT_TOKEN: str = _require_env("BOT_TOKEN")
OWNER_ID: int = _require_int("OWNER_ID")
LLM_API_KEY: str = _require_env("LLM_API_KEY")

# Optional with defaults
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

DB_PATH: str = os.getenv("DB_PATH", "bot.db")
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "50"))

# Security limits
MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", "4000"))
RATE_LIMIT_MESSAGES_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_MESSAGES_PER_MINUTE", "20"))

SYSTEM_PROMPT_DEFAULT: str = os.getenv(
    "SYSTEM_PROMPT_DEFAULT",
    "You are a personal AI assistant. Reply to messages on behalf of the user. Never reveal you are an AI."
)
