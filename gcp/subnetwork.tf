locals {
  # bigbang will submit a CIDR in the 172.16.x/20 range
  cidrs             = cidrsubnets(var.my_cidr, 2, 2, 2, 3, 8)
  subnetwork_cidr   = local.cidrs[0] # 0.1 - 3.254, 22 b = 1022 hosts
  k8s_pod_cidr      = local.cidrs[1] # 4.1 - 7.254, 22 b = 1022 hosts
  k8s_services_cidr = local.cidrs[2] # 8.1 - 11.254, 22 b = 1022 hosts
  googserv_cidr     = local.cidrs[3] # 12.1 - 13.254, 23 b = 510 hosts
  master_ntwk_cidr  = local.cidrs[4] # 14.1 - 14.14, 28 b = 14 hosts
  starburst_address = cidrhost(local.subnetwork_cidr, 103)
  ranger_address    = cidrhost(local.subnetwork_cidr, 104)
}

#
# Place our new subnet in same VPC as the VPN.
#
resource "google_compute_subnetwork" "snet" {
  project       = data.google_project.project.project_id
  name          = "${var.network_name}-snet"
  region        = var.region
  network       = resource.google_compute_network.vpc.name
  ip_cidr_range = local.subnetwork_cidr

  secondary_ip_range {
    range_name    = "k8s-pod-range"
    ip_cidr_range = local.k8s_pod_cidr
  }

  secondary_ip_range {
    range_name    = "k8s-services-range"
    ip_cidr_range = local.k8s_services_cidr
  }

  private_ip_google_access = true
}

#
# Add in NAT routing from all instances and GKE nodes
#
resource "google_compute_router" "router" {
  name    = "${google_compute_subnetwork.snet.name}-router"
  region  = var.region
  network = resource.google_compute_network.vpc.self_link
  project = data.google_project.project.project_id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${google_compute_router.router.name}-nat"
  router                             = google_compute_router.router.name
  region                             = google_compute_router.router.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  project                            = data.google_project.project.project_id
}
