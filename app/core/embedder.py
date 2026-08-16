"""可插拔 Embedder。

默认 Provider = mock_hash：确定性 hashing embedding（字符 n-gram + hashing trick），
不依赖网络/模型下载，用于验证 Pipeline 正确性。语义表达能力弱于真实模型——
它本质是一种"词/字面重合度"的向量化，对关键词类查询有一定效果，
对纯语义改写（同义but完全不同措辞）几乎无能力，这一点必须在评测报告中如实说明，
不能把它跑出来的 Recall 数字当作"生产级 Embedding 模型"的效果。

生产可切换 EMBEDDER_PROVIDER=openai，接口不变。
"""
import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.core.config import settings


def _ngrams(text: str, n: int = 2) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip().lower())
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


class Embedder(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class MockHashEmbedder(Embedder):
    """字符 2-gram + 3-gram hashing trick，L2归一化。确定性、无外部依赖。"""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _vectorize(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        grams = _ngrams(text, 2) + _ngrams(text, 3)
        for g in grams:
            h = hashlib.md5(g.encode("utf-8")).hexdigest()
            idx = int(h[:8], 16) % self.dim
            sign = 1.0 if int(h[8:9], 16) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(t) for t in texts]


class OpenAIEmbedder(Embedder):
    def __init__(self, dim: int = 1536, model: str = "text-embedding-3-small"):
        from openai import OpenAI  # lazy import，未安装/未配key时不影响mock路径

        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDER_PROVIDER=openai 但未配置 OPENAI_API_KEY")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    if settings.embedder_provider == "openai":
        return OpenAIEmbedder()
    return MockHashEmbedder(dim=settings.embedder_dim)
