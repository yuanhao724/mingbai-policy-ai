from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Mori"
    version: str = "1.0.0"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    openai_model: str = os.getenv("MORI_MODEL", "gpt-4o-mini")
    db_path: Path = Path(os.getenv("MORI_DB_PATH", str(BACKEND_DIR / "data" / "mori.db")))
    frontend_dir: Path = PROJECT_DIR / "frontend"
    sample_dir: Path = BACKEND_DIR / "sample_docs"
    top_k: int = _env_int("MORI_TOP_K", 4)
    chunk_size: int = _env_int("MORI_CHUNK_SIZE", 420)
    chunk_overlap: int = _env_int("MORI_CHUNK_OVERLAP", 70)
    stream_delay: float = _env_float("MORI_STREAM_DELAY", 0.012)
    manual_minutes_per_query: float = _env_float("MORI_MANUAL_MINUTES", 6.0)
    min_assistant_minutes: float = _env_float("MORI_MIN_ASSISTANT_MINUTES", 0.5)
    manual_minutes_per_policy: float = _env_float("MORI_MANUAL_MINUTES_PER_POLICY", 30.0)
    assistant_minutes_per_policy: float = _env_float("MORI_ASSISTANT_MINUTES_PER_POLICY", 5.0)
    max_upload_mb: int = _env_int("MORI_MAX_UPLOAD_MB", 8)
    max_history_turns: int = _env_int("MORI_MAX_HISTORY_TURNS", 8)

    @property
    def mode(self) -> str:
        return "openai" if self.openai_api_key else "local"


settings = Settings()
