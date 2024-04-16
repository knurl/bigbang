/*
 * We need to create a service account with authority to access our storage
 * bucket, and associate with our GKE cluster nodes.
 */
resource "google_service_account" "gke_servacct" {
  project    = data.google_project.project.project_id
  account_id = "${var.cluster_name}-servacct"
}

resource "google_service_account_key" "gke_servacct_key" {
  service_account_id = google_service_account.gke_servacct.id
  depends_on         = [google_service_account.gke_servacct]
}

resource "google_container_cluster" "gke" {
  project             = data.google_project.project.project_id
  name                = var.cluster_name
  location            = var.zone
  deletion_protection = false

  # We can't create a cluster with no node pool defined, but we want to only
  # use separately managed node pools. So we create the smallest possible
  # default node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  # subnet for nodes
  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.snet.name

  ip_allocation_policy {
    cluster_secondary_range_name  = google_compute_subnetwork.snet.secondary_ip_range[0].range_name # pods
    services_secondary_range_name = google_compute_subnetwork.snet.secondary_ip_range[1].range_name # services
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = local.master_ntwk_cidr
  }

  #
  # If private endpoint is enabled, then the public endpoint is automatically
  # disabled and it becomes mandatory to enable master authorised networks,
  # which will be applied to the private endpoint.
  #
  master_authorized_networks_config {
    cidr_blocks {
      # Only allow access to K8S control plane from the subnet we're running on
      cidr_block   = google_compute_subnetwork.snet.ip_cidr_range
      display_name = "Access from GKE private subnet"
    }
  }

  resource_labels = var.tags

}

resource "google_container_node_pool" "node_pool" {
  project           = data.google_project.project.project_id
  name              = "${google_container_cluster.gke.name}-nodepool"
  location          = var.zone
  cluster           = google_container_cluster.gke.name
  node_count        = var.node_count
  max_pods_per_node = var.max_pods_per_node
  # TODO: add autoscaling

  node_config {
    machine_type = var.instance_types[0]
    preemptible  = var.capacity_type == "Spot" ? true : false

    # Google recommends custom service accounts that have cloud-platform scope
    # and permissions granted via IAM Roles.
    service_account = google_service_account.gke_servacct.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    tags            = ["load-balanced-backend"]
    labels          = var.tags
  }
}
