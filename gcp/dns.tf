resource "google_dns_managed_zone" "private_zone" {
  name     = "${var.network_name}-dns"
  project  = data.google_project.project.project_id
  dns_name = "az.starburstdata.net."
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
  name         = "bastion.az.starburstdata.net."
  type         = "A"
  rrdatas      = [local.bastion_address]
  ttl          = 3600
}

resource "google_dns_record_set" "ldap_a_record" {
  project      = data.google_project.project.project_id
  managed_zone = google_dns_managed_zone.private_zone.name
  name         = "ldap.az.starburstdata.net."
  type         = "A"
  rrdatas      = [local.ldap_address]
  ttl          = 3600
}

resource "google_dns_record_set" "starburst_a_record" {
  project      = data.google_project.project.project_id
  managed_zone = google_dns_managed_zone.private_zone.name
  name         = "starburst.az.starburstdata.net."
  type         = "A"
  rrdatas      = [var.upstream_stargate ? local.bastion_address : local.starburst_address]
  ttl          = 3600
}
