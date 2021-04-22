data "google_project" "project" {
  project_id = "field-engineering-308119"
}

resource "google_project_iam_member" "gke_node_bq" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.gke_servacct.email}"
}
