from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aiops:aiops@localhost:5433/aiops"

    embedder_provider: str = "mock_hash"
    embedder_dim: int = 384
    openai_api_key: str = ""

    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    agent_max_iterations: int = 5
    agent_timeout_s: float = 30.0

    retriever_top_k_candidate: int = 30
    retriever_top_k_final: int = 5

    reranker_provider: str = "heuristic"  # heuristic（默认，无外部依赖） | cross_encoder


settings = Settings()
