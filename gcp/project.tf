data "google_project" "project" {
  project_id = var.gcp_project_id
}

resource "google_project_iam_binding" "bq_data_editor" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.dataOwner"

  members = [
    "user:${var.gcp_account}",
    "serviceAccount:${google_service_account.gke_servacct.email}",
  ]
}

resource "google_project_iam_binding" "bq_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.user"

  members = [
    "user:${var.gcp_account}",
    "serviceAccount:${google_service_account.gke_servacct.email}",
  ]
}
