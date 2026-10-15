from __future__ import annotations

import os
import json
from pathlib import Path
from google import genai

# ── Diretórios do Segundo Cérebro ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SECOND_BRAIN_DIR = BASE_DIR / "second_brain"
CACHE_DIR = SECOND_BRAIN_DIR / ".cache"
DB_PATH = CACHE_DIR / "memory_index.db"
MEMORY_MAP_PATH = SECOND_BRAIN_DIR / "MEMORY_MAP.md"

# Garante a existência dos diretórios fundamentais
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SECOND_BRAIN_DIR.mkdir(parents=True, exist_ok=True)

# ── Roteamento de Modelos Gemini (Model Tiering) ──────────────────────────
from .router import (
    ROUTE_BACKGROUND,
    ROUTE_FAST,
    ROUTE_REASONING,
    ROUTE_SEARCH,
    ledger,
    get_api_key as get_gemini_api_key,
    get_genai_client,
)

# Modelos padrão de referência
MODEL_PRIMARY: str = os.environ.get("GEMINI_PRIMARY_MODEL", "gemini-3.8-flash")
MODEL_LIGHTWEIGHT: str = os.environ.get("GEMINI_LIGHTWEIGHT_MODEL", "gemini-3.5-flash-lite")


def get_gemini_api_key() -> str:
    """Recupera a chave de API do Gemini a partir do ambiente ou do arquivo de configuração local."""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    # Tenta obter do config/api_keys.json do Mark-LV
    cfg_file = BASE_DIR / "config" / "api_keys.json"
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            key = str(data.get("gemini_api_key") or "").strip()
            if key:
                return key
        except Exception:
            pass

    return ""
