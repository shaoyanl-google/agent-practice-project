import json
import datetime
import sys
import re
from typing import Any, Optional

class StructuredLogger:
    def __init__(self, service_name: str = "chore-planning-agent"):
        self.service_name = service_name

    def redact_pii(self, text: str) -> str:
        """Redacts emails, phone numbers, and authorization tokens from text to guarantee privacy."""
        if not isinstance(text, str):
            return text
        # Redact emails
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', text)
        # Redact phone numbers
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', text)
        # Redact Google API OAuth / Access Tokens
        text = re.sub(r'\bya29\.[a-zA-Z0-9_-]+\b', '[REDACTED_OAUTH_TOKEN]', text)
        return text

    def _redact_dict(self, d: Any) -> Any:
        if isinstance(d, dict):
            return {k: self._redact_dict(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._redact_dict(x) for x in d]
        elif isinstance(d, str):
            return self.redact_pii(d)
        return d

    def log(self, level: str, event: str, message: Optional[str] = None, extra: Optional[dict[str, Any]] = None):
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level.upper(),
            "service": self.service_name,
            "event": event,
        }
        if message:
            log_entry["message"] = self.redact_pii(message)
        if extra:
            log_entry["data"] = self._redact_dict(extra)
        
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
        # Pre-redact query before classification to ensure safe classification
        query_redacted = self.redact_pii(user_query)
        query_lower = query_redacted.lower()
        if any(w in query_lower for w in ["schedule", "add", "calendar", "put", "set"]):
            return "schedule_chore"
        if any(w in query_lower for w in ["list", "show", "get", "view", "what"]):
            return "view_chores"
        return "general_query"
