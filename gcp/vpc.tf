resource "google_compute_network" "vpc" {
  project                 = data.google_project.project.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

# For SQL instances and other Google services to be accessed privately, we need
# to create a peering connection ourselves between our VPC and the Google VPC
resource "google_compute_global_address" "googserv_gaddrs" {
  project       = data.google_project.project.project_id
  name          = "${var.cluster_name}-googserv-gaddrs"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  network       = resource.google_compute_network.vpc.id
  address       = split("/", local.googserv_cidr)[0]
  prefix_length = split("/", local.googserv_cidr)[1]
}

resource "google_service_networking_connection" "pvpc_peering" {
  network                 = resource.google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.googserv_gaddrs.name]
}
