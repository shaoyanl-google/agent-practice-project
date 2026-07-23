provider "google" {
  project = var.project_id
  region  = var.region
}

# --- 1. ENABLE REQUIRED APIS ---
resource "google_project_service" "calendar_api" {
  service            = "calendar-json.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secret_manager_api" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# --- 2. IAM SERVICE ACCOUNT FOR AGENT EXECUTION ---
resource "google_service_account" "agent_runner" {
  account_id   = "chore-planning-agent-sa"
  display_name = "Chore Planning Agent Service Account"
}

# Grant the Service Account the ability to write to the logs
resource "google_project_iam_member" "logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

# --- 3. SECURE SECRET STORAGE (SECRET MANAGER) ---
# Create Secret Manager secret for the Gemini API Key
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"

  replication {
    auto {}
  }
  
  depends_on = [google_project_service.secret_manager_api]
}

# Grant the agent service account permission to access the secret
resource "google_secret_manager_secret_iam_member" "agent_secret_accessor" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runner.email}"
}
