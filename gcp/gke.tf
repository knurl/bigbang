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
  depends_on = [google_service_account.gke_servacct]
}

resource "google_container_cluster" "gke" {
  project                         = data.google_project.project.project_id
  name                            = var.cluster_name
  location                        = var.zone
  initial_node_count              = var.node_count
  default_max_pods_per_node       = 16

  # subnet for nodes
  subnetwork                      = google_compute_subnetwork.snet.self_link

  ip_allocation_policy {
    cluster_secondary_range_name  = google_compute_subnetwork.snet.secondary_ip_range[0].range_name # pods
    services_secondary_range_name = google_compute_subnetwork.snet.secondary_ip_range[1].range_name # services
  }

  private_cluster_config {
    enable_private_nodes          = true
    enable_private_endpoint       = true
    master_ipv4_cidr_block        = local.master_ntwk_cidr
  }

  #
  # If private endpoint is enabled, then the public endpoint is automatically
  # disabled and it becomes mandatory to enable master authorised networks,
  # which will be applied to the private endpoint.
  # TODO: Do we still need this here to work?
  #
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block                  = "10.0.0.0/8"
      display_name                = "Class_A"
    }
    cidr_blocks {
      cidr_block                  = "172.16.0.0/12"
      display_name                = "Class_B"
    }
    cidr_blocks {
      cidr_block                  = "192.168.0.0/16"
      display_name                = "Class_C"
    }
  }

  node_config {
    machine_type                  = var.instance_type
    service_account               = google_service_account.gke_servacct.email
    oauth_scopes                  = ["https://www.googleapis.com/auth/cloud-platform"]
    labels                        = var.tags
  }
  resource_labels                 = var.tags

  # This dependency can be necessary during destroys to avoid connections to the
  # databases that prevent them from being destroyed.
  # https://github.com/hashicorp/terraform-provider-google/issues/3820
  #
  #  depends_on = [
  #    google_service_account.gke_servacct,
  #    google_sql_database.db_evtlog,
  #    google_sql_database.db_postgres,
  #    google_sql_database.db_mysql
  #  ]
}
