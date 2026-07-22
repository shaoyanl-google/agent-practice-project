import json
import datetime
import sys
from typing import Any, Optional

class StructuredLogger:
    def __init__(self, service_name: str = "chore-planning-agent"):
        self.service_name = service_name

    def log(self, level: str, event: str, message: Optional[str] = None, extra: Optional[dict[str, Any]] = None):
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level.upper(),
            "service": self.service_name,
            "event": event,
        }
        if message:
            log_entry["message"] = message
        if extra:
            # Merge extra keys directly or nest under "data"
            log_entry["data"] = extra
        
        # Write structured JSON log to stdout
        sys.stdout.write(f"\n--- [LOG] {json.dumps(log_entry)} ---\n")
        sys.stdout.flush()

    def info(self, event: str, message: Optional[str] = None, extra: Optional[dict[str, Any]] = None):
        self.log("INFO", event, message, extra)

    def error(self, event: str, message: Optional[str] = None, extra: Optional[dict[str, Any]] = None):
        self.log("ERROR", event, message, extra)

    def warning(self, event: str, message: Optional[str] = None, extra: Optional[dict[str, Any]] = None):
        self.log("WARNING", event, message, extra)

    def classify_intent(self, user_query: str) -> str:
        query_lower = user_query.lower()
        if any(w in query_lower for w in ["schedule", "add", "calendar", "put", "set"]):
            return "schedule_chore"
        if any(w in query_lower for w in ["list", "show", "get", "view", "what"]):
            return "view_chores"
        return "general_query"
