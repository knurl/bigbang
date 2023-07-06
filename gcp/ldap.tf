resource "google_compute_instance" "ldaps" {
  name         = var.ldaps_name
  machine_type = var.small_instance_type
  zone         = var.zone
  project      = data.google_project.project.project_id
  tags         = ["ldaps"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.snet.self_link
    network_ip = local.ldap_address
  }

  metadata = {
    ssh-keys                   = "ubuntu:${var.ssh_public_key}"
    serial-port-logging-enable = "TRUE"
  }

  metadata_startup_script = file(var.ldaps_launch_script)
  labels                  = var.tags

  /* We have a dependency on our NAT gateway for outbound connectivity during
   * our launch script, as well as DNS so that certificates can be validated.
   */
  depends_on = [google_compute_router_nat.nat, google_dns_record_set.ldap_a_record]
}

resource "google_compute_firewall" "fw-ldaps" {
  name    = "${var.ldaps_name}-fw"
  network = resource.google_compute_network.vpc.self_link
  project = data.google_project.project.project_id
  # Restrict to private IPs
  source_ranges = [var.my_cidr]
  allow {
    protocol = "tcp"
    ports    = ["22", "636"]
  }
  target_tags = ["ldaps"]
}
