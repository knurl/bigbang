resource "google_dns_managed_zone" "private_zone" {
  name     = "${var.network_name}-dns"
  project  = data.google_project.project.project_id
  dns_name = var.domain
  labels   = var.tags

  visibility = "private"

  private_visibility_config {
    networks {
      network_url = resource.google_compute_network.vpc.id
    }
  }
}

resource "google_dns_record_set" "bastion_a_record" {
  project      = data.google_project.project.project_id
  managed_zone = google_dns_managed_zone.private_zone.name
  name         = "bastion.hazelcast.net."
  type         = "A"
  rrdatas      = [local.bastion_address]
  ttl          = 3600
}

