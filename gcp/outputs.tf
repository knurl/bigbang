output "k8s_api_server" {
  value = google_container_cluster.gke.endpoint
}

output "bastion_address" {
  value = google_compute_instance.bastion.network_interface.0.access_config.0.nat_ip
}

output "object_key" {
  value     = base64decode(google_service_account_key.gke_servacct_key.private_key)
  sensitive = true
}
