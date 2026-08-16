"""Tool 抽象接口：Agent Runtime 只依赖这个契约，不关心内部实现。

统一契约意味着新增一个Tool（比如未来的Ticket工单查询）不需要改动Agent Loop
一行代码——这是"Tool Layer"和"Agent Layer"边界划分的具体体现。
"""
import time
from abc import ABC, abstractmethod

from app.core.types import ToolResult, ToolSpec


class Tool(ABC):
    name: str
    description: str
    input_schema: dict

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema=self.input_schema)

    @abstractmethod
    def _call(self, **kwargs) -> ToolResult: ...

    def call(self, **kwargs) -> ToolResult:
        """统一包装计时和异常捕获，避免每个Tool自己重复写try/except。"""
        start = time.perf_counter()
        try:
            result = self._call(**kwargs)
        except Exception as exc:  # noqa: BLE001 - Tool失败是预期场景,不能让异常打断Agent Loop
            result = ToolResult(success=False, summary="", error=str(exc))
        result.latency_ms = (time.perf_counter() - start) * 1000
        return result
