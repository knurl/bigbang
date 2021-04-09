resource "google_bigquery_dataset" "dataset" {
  project                    = data.google_project.project.project_id
  dataset_id                 = var.db_name
  location                   = var.region
  delete_contents_on_destroy = true

  access {
    role                     = "OWNER"
    user_by_email            = google_service_account.gke_servacct.email
  }

  labels                     = var.tags
}
