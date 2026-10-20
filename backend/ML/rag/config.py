from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    chat_model: str = field(default_factory=lambda: os.getenv("RAG_CHAT_MODEL", "qwen3:4b-instruct"))
    embedding_model: str = field(default_factory=lambda: os.getenv("RAG_EMBEDDING_MODEL", "embeddinggemma:300m"))
    corpus_dir: Path = field(default_factory=lambda: Path(os.getenv("RAG_CORPUS_DIR", "corpus")))
    index_path: Path = field(default_factory=lambda: Path(os.getenv("RAG_INDEX_PATH", "data/index.json")))
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4
    min_similarity: float = 0.35
    timeout_seconds: float = 180