"""结构化日志：每条日志都是一行 JSON，贯穿 request_id，便于按 request_id grep 出完整链路。

offline_app.py 额外把日志写到 logs/offline_app.log 这个文件——这不只是为了排查问题，
是 data/real/self_logs.py 的数据来源：让 log_query Tool 在查"这个系统自己"的时候，
返回的是这个进程真实写下的日志，不是编的数据。"""
import json
import logging
import sys
import time
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "agent_run_id", "tool_name", "latency_ms", "stage"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
