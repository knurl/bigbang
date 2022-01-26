output "k8s_api_server" {
  value = google_container_cluster.gke.endpoint
}

output "bastion_address" {
  value = google_compute_instance.bastion.network_interface.0.access_config.0.nat_ip
}

output "ldaps_address" {
  value = google_compute_instance.ldaps.network_interface.0.network_ip
}

output "starburst_address" {
  value = google_compute_address.starburst_static_ip.address
}

output "starburst_address_name" {
  value = google_compute_address.starburst_static_ip.name
}

output "ranger_address" {
  value = google_compute_address.ranger_static_ip.address
}

output "evtlog_address" {
  value = google_sql_database_instance.sql_postgres.private_ip_address
}

output "hmsdb_address" {
  value = google_sql_database_instance.sql_postgres.private_ip_address
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
  value     = base64decode(google_service_account_key.gke_servacct_key.private_key)
  sensitive = true
}
