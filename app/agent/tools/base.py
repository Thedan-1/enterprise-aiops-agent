"""Tool 抽象接口：Agent Runtime 只依赖这个契约，不关心内部实现。

统一契约意味着新增一个Tool（比如未来的Ticket工单查询）不需要改动Agent Loop
一行代码——这是"Tool Layer"和"Agent Layer"边界划分的具体体现。
"""
import time
import inspect
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from app.core.types import ToolResult, ToolSpec


class TransientToolError(RuntimeError):
    """An adapter may raise this only when retrying the same read is safe."""


class Tool(ABC):
    name: str
    description: str
    input_schema: dict
    max_attempts: int = 2
    timeout_s: float = 5.0
    backoff_base_s: float = 0.05

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema=self.input_schema)

    @abstractmethod
    def _call(self, **kwargs) -> ToolResult: ...

    def call(self, **kwargs) -> ToolResult:
        """Apply a bounded timeout and retry only explicitly transient failures."""
        start = time.perf_counter()
        try:
            inspect.signature(self._call).bind(**kwargs)
        except TypeError as exc:
            return ToolResult(
                success=False,
                summary="",
                error=f"invalid tool input: {exc}",
                debug={"attempts": 0, "timed_out": False},
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        result: ToolResult | None = None
        attempts = 0
        timed_out = False
        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{self.name}")
            future = executor.submit(self._call, **kwargs)
            try:
                result = future.result(timeout=self.timeout_s)
                executor.shutdown(wait=True)
                break
            except FutureTimeoutError:
                timed_out = True
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                error = f"tool timeout after {self.timeout_s}s"
            except TransientToolError as exc:
                executor.shutdown(wait=True)
                error = str(exc)
            except Exception as exc:  # noqa: BLE001 - failure becomes an Observation
                executor.shutdown(wait=True)
                result = ToolResult(success=False, summary="", error=str(exc))
                break

            if attempt < self.max_attempts:
                time.sleep(self.backoff_base_s * (2 ** (attempt - 1)))
            else:
                result = ToolResult(success=False, summary="", error=error)

        if result is None:  # defensive: max_attempts must never produce no observation
            result = ToolResult(success=False, summary="", error="tool failed without result")
        result.debug = {**(result.debug or {}), "attempts": attempts, "timed_out": timed_out}
        result.latency_ms = (time.perf_counter() - start) * 1000
        return result
