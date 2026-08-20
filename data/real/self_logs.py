"""读取这个 AIOps Agent 进程自己真实写下的结构化日志（不是编的数据）。

日志文件由 app/core/logging.py 的 setup_logging(log_file=...) 写入，
app/offline_app.py 启动时指定路径为项目根目录下 logs/offline_app.log。
每条日志都是 JsonFormatter 输出的一行 JSON，直接解析回来展示。
"""
import json
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "offline_app.log"


def get_self_logs(level: str = "INFO", limit: int = 20) -> list[str]:
    if not LOG_PATH.exists():
        return []
    raw_lines = LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()

    out: list[str] = []
    for line in raw_lines[-1000:]:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if level and rec.get("level") != level.upper():
            continue
        extra = f" tool={rec['tool_name']}" if rec.get("tool_name") else ""
        latency = f" latency={rec['latency_ms']:.1f}ms" if rec.get("latency_ms") is not None else ""
        out.append(f"[{rec.get('logger', '')}] {rec.get('msg', '')}{extra}{latency}")
    return out[-limit:]
