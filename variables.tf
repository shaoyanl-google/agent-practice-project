variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID where the agent resources will be provisioned."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "The region to deploy computing and storage resources."
}
