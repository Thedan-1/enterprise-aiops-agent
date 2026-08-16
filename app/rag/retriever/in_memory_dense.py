"""离线/无数据库环境下的 Dense 检索：内存中用 cosine similarity 排序。

用途说明（不是为了展示技术花活，是这次沙箱环境的真实限制逼出来的）：
本机 Docker Desktop 依赖的 WSL2 因为宿主机未开启 Windows 的
"Virtual Machine Platform" 功能而无法启动（WSL_E_VIRTUAL_MACHINE_PLATFORM_REQUIRED），
这需要管理员权限+重启才能修复，不在自动化流程可以做的事情范围内。
为了仍然拿到真实（而不是继续等待或编造）的Pipeline运行数字，用这个内存实现
替代 DenseRetriever 对 Postgres 的依赖，检索逻辑（cosine排序）完全等价，
区别只在于"在数据库里排序"还是"在内存里线性扫描排序"——数据量小的时候
两者结果一致，数据量大起来后数据库版本能利用HNSW索引而内存版本退化为O(n)，
这正是 architecture.md ADR-001 里"数据规模决定是否需要专用索引"这个判断的
一个具体例证。生产路径 DenseRetriever(session, embedder) 代码已就绪，
宿主机能起Docker后直接切换,不用改Pipeline其余部分。
"""
from app.core.embedder import Embedder
from app.core.types import Chunk, ScoredChunk


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


class InMemoryDenseRetriever:
    def __init__(self, chunks: list[Chunk], embeddings: list[list[float]], embedder: Embedder):
        self.chunks = chunks
        self.embeddings = embeddings
        self.embedder = embedder

    def search(self, query: str, top_k: int = 30) -> list[ScoredChunk]:
        if not self.chunks:
            return []
        qvec = self.embedder.embed_one(query)
        scored = [(c, _cosine(qvec, e)) for c, e in zip(self.chunks, self.embeddings)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            ScoredChunk(chunk=c, score=float(s), rank=i + 1) for i, (c, s) in enumerate(scored[:top_k])
        ]
