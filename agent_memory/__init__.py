"""Agent Memory: Subsistema de Memória Persistente (Segundo Cérebro) para Assistentes de IA."""

from .config import (
    MODEL_PRIMARY,
    MODEL_LIGHTWEIGHT,
    SECOND_BRAIN_DIR,
    MEMORY_MAP_PATH,
    DB_PATH,
    get_genai_client,
)
from .tools import MemoryToolManager
from .indexer import MemorySearchEngine
from .extractor import MemoryIngestionWorker
from .consolidator import MemoryConsolidator

__all__ = [
    "MODEL_PRIMARY",
    "MODEL_LIGHTWEIGHT",
    "SECOND_BRAIN_DIR",
    "MEMORY_MAP_PATH",
    "DB_PATH",
    "get_genai_client",
    "MemoryToolManager",
    "MemorySearchEngine",
    "MemoryIngestionWorker",
    "MemoryConsolidator",
]
