"""One configuration surface; CPU defaults, no credentials in source."""
from pathlib import Path
from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', env_ignore_empty=True)
    data_dir: Path = Path('data')
    host: str = '0.0.0.0'
    port: int = 7860
    api_token: str = ''
    groq_api_key: str = ''
    llm_base_url: str = 'https://api.groq.com/openai/v1'
    llm_model: str = 'openai/gpt-oss-120b'
    small_model: str = 'openai/gpt-oss-20b'
    llm_timeout: float = 60
    llm_max_tokens: int = 4096
    small_input_usd_million: float | None = None
    small_output_usd_million: float | None = None
    large_input_usd_million: float | None = None
    large_output_usd_million: float | None = None
    qdrant_url: str = ''
    qdrant_api_key: str = ''
    collection: str = 'evidencegraph_x_v1'
    embedding_model: str = 'BAAI/bge-small-en-v1.5'
    embedding_threads: int = 2
    neo4j_uri: str = ''
    neo4j_user: str = 'neo4j'
    neo4j_password: str = ''
    neo4j_database: str = 'neo4j'
    redis_url: str = ''
    parser: Literal['pymupdf', 'docling'] = 'pymupdf'
    max_upload_mb: int = Field(30, ge=1, le=100)
    max_pages: int = Field(400, ge=1)
    chunk_words: int = Field(140, ge=20)
    parent_words: int = Field(700, ge=100)
    retrieval_k: int = Field(30, ge=10, le=100)
    reranker_k: int = Field(8, ge=5, le=20)
    reranker_model: str = 'ms-marco-TinyBERT-L-2-v2'
    use_reranker: bool = True
    graph_enabled: bool = True
    graph_chunk_limit: int = Field(0, ge=0)
    graph_request_interval: float = Field(60, ge=0, le=3600)
    graph_rate_limit_retries: int = Field(3, ge=0, le=10)
    graph_max_retry_wait: float = Field(60, ge=0, le=300)
    graph_hops: int = Field(2, ge=1, le=2)
    graph_limit: int = Field(1000, ge=10, le=10000)
    cache_threshold: float = Field(0.98, ge=0, le=1)
    semantic_cache: bool = False
    cache_ttl: int = Field(3600, ge=1)
    cache_entries: int = Field(50, ge=1, le=500)
    grade_threshold: float = Field(0.65, ge=0, le=1)
    max_context_chars: int = Field(26000, ge=2000)
    use_hyde: bool = False
    judge_base_url: str = 'https://api.openai.com/v1'
    judge_api_key: str = ''
    judge_model: str = ''

@lru_cache
def settings() -> Settings:
    return Settings()
