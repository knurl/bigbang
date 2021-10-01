resource "google_storage_bucket" "gcs_bucket" {
  project                     = data.google_project.project.project_id
  name                        = var.bucket_name
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
  labels                      = var.tags

  versioning {
    enabled = false
  }
}

resource "google_storage_bucket_iam_binding" "binding" {
  bucket  = google_storage_bucket.gcs_bucket.name
  role    = "roles/storage.admin"
  members = ["serviceAccount:${google_service_account.gke_servacct.email}"]
  /*
  depends_on = [
    google_storage_bucket.gcs_bucket,
    google_service_account.gke_servacct,
    google_container_cluster.gke
  ]
  */
}
