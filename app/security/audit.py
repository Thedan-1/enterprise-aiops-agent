from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AuditEvent:
    action: str
    outcome: str
    user_id: str
    tenant_id: str
    request_id: str = ""
    detail: str = ""
    ts: str = ""


class AuditStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: AuditEvent) -> None:
        payload = asdict(event)
        payload["ts"] = event.ts or datetime.now(timezone.utc).isoformat()
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_for_tenant(self, tenant_id: str, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("tenant_id") == tenant_id:
                rows.append(row)
        return rows[-limit:][::-1]

