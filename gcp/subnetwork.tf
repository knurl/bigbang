locals {
  # bigbang will submit a CIDR in the 172.16.x/20 range
  cidrs             = cidrsubnets(var.my_cidr, 2, 2, 2, 4, 4, 4, 8)
  subnetwork_cidr   = local.cidrs[0] # 0.1 - 3.254, 22 b = 1022 hosts
  k8s_pod_cidr      = local.cidrs[1] # 4.1 - 7.254, 22 b = 1022 hosts
  k8s_services_cidr = local.cidrs[2] # 8.1 - 11.254, 22 b = 1022 hosts
  googserv_cidr     = local.cidrs[3] # 12.1 - 12.254, 24 b = 254 hosts
  proxy_ntwk_cidr   = local.cidrs[4] # 13.1 - 13.254, 24 b = 254 hosts
  ilb_cidr          = local.cidrs[5] # 14.1 - 14.254, 24 b = 254 hosts
  master_ntwk_cidr  = local.cidrs[6] # 15.1 - 15.16, 28 b = 16 hosts
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

/*
 * Preserve the static internal IP for Starburst and Ranger.
 */

# Starburst
resource "google_compute_address" "starburst_static_ip" {
  project      = data.google_project.project.project_id
  name         = "starburst-static-ip"
  subnetwork   = google_compute_subnetwork.snet.id
  address_type = "INTERNAL"
  address      = local.starburst_address
  region       = var.region
}

# Ranger
resource "google_compute_address" "ranger_static_ip" {
  project      = data.google_project.project.project_id
  name         = "ranger-static-ip"
  subnetwork   = google_compute_subnetwork.snet.id
  address_type = "INTERNAL"
  address      = local.ranger_address
  region       = var.region
}

/*
 * We need 2 new subnets in order to allow for *internal* HTTP(S)
 * load-balancers that we're positioning in front of Starburst.
 */

# proxy-only subnet
resource "google_compute_subnetwork" "proxy_subnet" {
  project       = data.google_project.project.project_id
  name          = "${var.network_name}-proxy-snet"
  region        = var.region
  network       = resource.google_compute_network.vpc.name
  ip_cidr_range = local.proxy_ntwk_cidr
  purpose       = "INTERNAL_HTTPS_LOAD_BALANCER"
  role          = "ACTIVE" # alternative is BACKUP
}

# backend subnet
resource "google_compute_subnetwork" "ilb_subnet" {
  project       = data.google_project.project.project_id
  name          = "${var.network_name}-ilb-snet"
  region        = var.region
  network       = resource.google_compute_network.vpc.name
  ip_cidr_range = local.ilb_cidr
  purpose       = "PRIVATE"
}

/*
 * Firewall rules for new subnets
 */

# allow all access from IAP and health check ranges
resource "google_compute_firewall" "fw-iap" {
  project       = data.google_project.project.project_id
  name          = "l7-ilb-fw-allow-iap-hc"
  direction     = "INGRESS"
  network       = google_compute_network.vpc.name
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16", "35.235.240.0/20"]
  target_tags   = ["load-balanced-backend"]
  allow {
    protocol = "tcp"
  }
}

# allow http from proxy subnet to backends
resource "google_compute_firewall" "fw-ilb-to-backends" {
  project       = data.google_project.project.project_id
  name          = "l7-ilb-fw-allow-ilb-to-backends"
  direction     = "INGRESS"
  network       = google_compute_network.vpc.name
  source_ranges = [google_compute_subnetwork.proxy_subnet.ip_cidr_range]
  target_tags   = ["load-balanced-backend"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8080"]
  }
}

#
# Add in NAT routing from all instances and GKE nodes
#
resource "google_compute_router" "router" {
  project = data.google_project.project.project_id
  name    = "${google_compute_subnetwork.snet.name}-router"
  region  = var.region
  network = resource.google_compute_network.vpc.self_link
}

resource "google_compute_router_nat" "nat" {
  project = data.google_project.project.project_id
  name    = "${google_compute_router.router.name}-nat"
  router  = google_compute_router.router.name
  region  = google_compute_router.router.region

  nat_ip_allocate_option = "AUTO_ONLY"

  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
