"""Append-only JSONL audit logger."""
import json
from datetime import datetime, timezone
from core.config import AUDIT_DIR


class AuditLogger:
    def __init__(self, run_id: str):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.log_path = AUDIT_DIR / f"{run_id}.jsonl"

    def log(self, agent: str, action: str, **kwargs) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id, "agent": agent, "action": action, **kwargs}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def get_logs(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
