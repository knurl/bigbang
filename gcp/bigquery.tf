# In order for the service users associated with the GKE nodes to be allowed to
# initiate reads, we have to grant them BigQuery 'user' privileges.
resource "google_project_iam_member" "bqread" {
  project    = data.google_project.project.project_id
	role       = "roles/bigquery.user"
  member     = "serviceAccount:${google_service_account.gke_servacct.email}"
}
