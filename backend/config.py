"""
config.py
────────────────────────────────────────────────────────────────────────────────
Central application configuration using Pydantic Settings.

WHY PYDANTIC SETTINGS?
  `pydantic-settings` reads values from environment variables (or a .env file)
  and validates + type-converts them automatically. Instead of doing:

      import os
      api_key = os.getenv("GEMINI_API_KEY")   # returns None silently if missing

  We get:

      from config import settings
      settings.gemini_api_key    # raises clear error if missing

  This catches missing config at startup — before anything breaks mid-request.

HOW IT WORKS:
  1. Pydantic reads fields defined in the Settings class.
  2. For each field, it looks for a matching env variable (case-insensitive).
  3. If the .env file exists, it's loaded automatically.
  4. If a required field is missing, it raises a ValidationError with a
     clear message telling you exactly which variable is absent.

USAGE (anywhere in the codebase):
    from config import settings

    print(settings.gemini_api_key)
    print(settings.neo4j_uri)
────────────────────────────────────────────────────────────────────────────────
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    All application settings loaded from environment variables / .env file.

    Pydantic Settings automatically:
      - Reads from environment variables (case-insensitive)
      - Falls back to .env file if present
      - Validates types (e.g. int fields won't accept "abc")
      - Raises clear errors for missing required fields
    """

    model_config = SettingsConfigDict(
        # Load from .env file if it exists (won't error if file is absent)
        env_file=".env",
        env_file_encoding="utf-8",
        # Ignore extra variables in the .env file
        extra="ignore",
    )

    # ── Google Gemini ─────────────────────────────────────────────────────────
    gemini_api_key: str = Field(
        ...,  # ... means required — app won't start without this
        description="Google Gemini API key from Google AI Studio.",
    )

    gemini_model: str = Field(
        default="gemini-1.5-flash",
        description=(
            "Gemini model to use. "
            "'gemini-1.5-flash' is fast and cost-efficient. "
            "'gemini-1.5-pro' is more capable but slower/costlier."
        ),
    )

    # ── Neo4j Graph Database ──────────────────────────────────────────────────
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description=(
            "Neo4j connection URI. "
            "Use 'bolt://localhost:7687' for local Docker. "
            "Use 'bolt+s://...' for Neo4j AuraDB (cloud)."
        ),
    )

    neo4j_username: str = Field(
        default="neo4j",
        description="Neo4j database username.",
    )

    neo4j_password: str = Field(
        ...,  # required
        description="Neo4j database password.",
    )

    # ── File Storage ──────────────────────────────────────────────────────────
    upload_dir: str = Field(
        default="./uploads",
        description="Local directory where uploaded PDFs are stored.",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = Field(
        default="development",
        description="Environment: 'development' or 'production'.",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR.",
    )


# ── Lazy singleton ───────────────────────────────────────────────────────────
# We use a lazy getter instead of instantiating at module import time.
#
# WHY LAZY: If settings = Settings() runs at import time, every module that
# does `from config import settings` would fail immediately if the .env file
# is missing — even during testing. Lazy loading means Settings() is only
# called the first time get_settings() is invoked (i.e. when the app actually
# starts, not when the module is imported).
#
# USAGE — anywhere in the codebase:
#   from config import get_settings
#   settings = get_settings()
#   print(settings.gemini_api_key)

_settings_instance: "Settings | None" = None


def get_settings() -> Settings:
    """
    Returns the shared Settings instance, creating it on first call.

    Raises:
        pydantic_core.ValidationError: If required env vars are missing.
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
