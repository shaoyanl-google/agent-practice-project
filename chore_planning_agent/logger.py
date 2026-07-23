import json
import datetime
import sys
import re
import httpx
from typing import Any, Optional
from google.auth import default
from google.auth.transport.requests import Request

class StructuredLogger:
    def __init__(self, service_name: str = "chore-planning-agent"):
        self.service_name = service_name

    def redact_pii_regex(self, text: str) -> str:
        """Fallback local regex-based PII redaction."""
        if not isinstance(text, str):
            return text
        # Redact emails
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', text)
        # Redact phone numbers
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', text)
        # Redact Google API OAuth / Access Tokens
        text = re.sub(r'\bya29\.[a-zA-Z0-9_-]+\b', '[REDACTED_OAUTH_TOKEN]', text)
        return text

    def redact_pii_dlp(self, text: str) -> str:
        """Uses Google Cloud DLP (Sensitive Data Protection) API to redact sensitive PII.
        
        Falls back to local regex-based redaction on API error or authorization failure.
        """
        if not isinstance(text, str) or not text.strip():
            return text
            
        try:
            scopes = ["https://www.googleapis.com/auth/cloud-platform"]
            creds, project = default(scopes=scopes)
            if creds:
                if not creds.valid:
                    creds.refresh(Request())
                
                url = f"https://dlp.googleapis.com/v2/projects/{project}/content:deidentify"
                headers = {
                    "Authorization": f"Bearer {creds.token}",
                    "Content-Type": "application/json"
                }
                
                body = {
                    "item": {
                        "value": text
                    },
                    "deidentifyConfig": {
                        "infoTypeTransformations": {
                            "transformations": [
                                {
                                    "infoTypes": [
                                        {"name": "EMAIL_ADDRESS"},
                                        {"name": "PHONE_NUMBER"},
                                        {"name": "IP_ADDRESS"},
                                        {"name": "CREDIT_CARD_NUMBER"}
                                    ],
                                    "primitiveTransformation": {
                                        "replaceConfig": {
                                            "newValue": {
                                                "stringValue": "[REDACTED]"
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
                
                with httpx.Client() as client:
                    response = client.post(url, headers=headers, json=body, timeout=5.0)
                    
                if response.status_code == 200:
                    result = response.json()
                    redacted = result.get("item", {}).get("value")
                    if redacted:
                        return redacted
        except Exception:
            pass
            
        return self.redact_pii_regex(text)

    def redact_pii(self, text: str) -> str:
        """Active PII redaction pipeline entry point (DLP API with local fallback)."""
        return self.redact_pii_dlp(text)

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
        query_redacted = self.redact_pii(user_query)
        query_lower = query_redacted.lower()
        if any(w in query_lower for w in ["schedule", "add", "calendar", "put", "set"]):
            return "schedule_chore"
        if any(w in query_lower for w in ["list", "show", "get", "view", "what"]):
            return "view_chores"
        return "general_query"
