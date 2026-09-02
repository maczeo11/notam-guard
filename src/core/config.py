"""Single source of configuration.

Every environment variable in the project is read here and nowhere else, so
defaults cannot drift between modules (they previously did: DATABASE_URL was
defaulted in both ingest.py and the pgvector adapter).
"""
from dataclasses import dataclass, field
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(*names: str, default: str | None = None) -> str | None:
    """First set variable among `names`.

    LangSmith renamed its variables from LANGCHAIN_* to LANGSMITH_*; the SDK
    honours both, so this reads both rather than silently disabling tracing for
    anyone who follows the current documentation.
    """
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _env_bool(*names: str, default: bool) -> bool:
    raw = _env(*names)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", "postgresql://notam:notam@localhost:5432/notam"))
    redis_url: str = field(default_factory=lambda: os.getenv(
        "REDIS_URL", "redis://localhost:6379/0"))
    redis_connect_timeout: int = 1

    vector_adapter: str = field(default_factory=lambda: os.getenv("VECTOR_ADAPTER", "pgvector"))
    embedding_model: str = field(default_factory=lambda: os.getenv(
        "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))
    retrieval_k: int = field(default_factory=lambda: int(os.getenv("RETRIEVAL_K", "3")))

    llm_adapter: str = field(default_factory=lambda: os.getenv(
        "LLM_ADAPTER", "groq" if os.getenv("GROQ_API_KEY") else "rule"))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    groq_api_key: str | None = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))

    notam_dir: Path = field(default_factory=lambda: Path(
        os.getenv("NOTAM_DIR", str(REPO_ROOT / "data" / "notams"))))

    # Safety policy. A verdict at or below this confidence is never auto-approved.
    human_gate_confidence: float = field(
        default_factory=lambda: float(os.getenv("HUMAN_GATE_CONFIDENCE", "0.75")))
    ticket_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("TICKET_TTL_SECONDS", "86400")))
    history_length: int = 5

    # DGCA CAR Section 3 §7: micro RPA ceiling.
    max_agl_m: int = field(default_factory=lambda: int(os.getenv("MAX_AGL_M", "120")))

    tracing_enabled: bool = field(default_factory=lambda: _env_bool(
        "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", default=False))
    tracing_api_key: str | None = field(default_factory=lambda: _env(
        "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Drop the cached Settings so tests can re-read a patched environment."""
    global _settings
    _settings = None
