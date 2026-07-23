import os
import base64
import httpx
from google.auth import default
from google.auth.transport.requests import Request

def load_google_api_key(secret_id: str = "gemini-api-key") -> str:
    """Loads the Google Gemini API key securely from Google Secret Manager via REST API.
    
    If Secret Manager is unavailable or unauthorized, falls back to the local
    environment variable or .env file configuration.
    """
    # 1. Attempt to fetch from Secret Manager using REST API with ADC credentials
    try:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        creds, project = default(scopes=scopes)
        if creds:
            if not creds.valid:
                creds.refresh(Request())
            
            url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets/{secret_id}/versions/latest:access"
            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json"
            }
            
            with httpx.Client() as client:
                response = client.get(url, headers=headers, timeout=5.0)
                
            if response.status_code == 200:
                data = response.json()
                payload_b64 = data["payload"]["data"]
                secret_val = base64.b64decode(payload_b64).decode("utf-8").strip()
                if secret_val:
                    # Set in environment to let Google ADK pick it up
                    os.environ["GOOGLE_API_KEY"] = secret_val
                    return secret_val
    except Exception:
        # Graceful fallback to local config on any retrieval/auth error
        pass

    # 2. Fall back to environment variable or local .env file
    val = os.environ.get("GOOGLE_API_KEY")
    if val:
        return val
        
    return ""
