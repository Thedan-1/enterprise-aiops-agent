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
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    agent_max_iterations: int = 5
    agent_timeout_s: float = 30.0

    retriever_top_k_candidate: int = 30
    retriever_top_k_final: int = 5

    reranker_provider: str = "heuristic"  # heuristic（默认，无外部依赖） | cross_encoder
    reranker_min_score: float = 0.5  # 低于此分数的证据视为"不相关"，不进Evidence（见ADR-005，防止幻觉的关键阈值）


settings = Settings()
