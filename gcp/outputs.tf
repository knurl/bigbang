output "bastion_address" {
  value = google_compute_instance.bastion.network_interface.0.network_ip
}

output "evtlog_address" {
  value = google_sql_database_instance.sql_evtlog.private_ip_address
}

output "postgres_address" {
  value = google_sql_database_instance.sql_postgres.private_ip_address
}

output "mysql_address" {
  value = google_sql_database_instance.sql_mysql.private_ip_address
}

output "object_address" {
  value = google_storage_bucket.gcs_bucket.url
}

output "object_key" {
  value = base64decode(google_service_account_key.gke_servacct_key.private_key)
}

output "bq_project_id" {
  #  value = data.google_project.project.project_id
  value = "bigquery-public-data"
}
