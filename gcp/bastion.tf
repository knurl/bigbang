data "google_compute_image" "ubuntu" {
  family  = "ubuntu-1804-lts"
  project = "ubuntu-os-cloud"
}

resource "google_compute_instance" "bastion" {
  name         = "bastion"
  machine_type = var.bastion_instance_type
  zone         = var.zone
  project      = data.google_project.project.project_id
  tags         = ["bastion"]

  boot_disk {
    initialize_params {
      image    = data.google_compute_image.ubuntu.self_link
    }
  }

  metadata     = {
    sshKeys    = "ubuntu:${file("~/.ssh/id_rsa.pub")}"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.snet.self_link
    network_ip = cidrhost(local.subnetwork_cidr, 102)
  }

  labels       = var.tags
}

resource "google_compute_firewall" "fw-bastion" {
  name        = "fw-bastion"
  network     = data.google_compute_network.vpc.self_link
  project     = data.google_project.project.project_id
  # Restrict to home IP or VPN
  source_ranges = ["${var.my_public_ip}/32", "10.0.0.0/8"]
  allow {
    protocol  = "tcp"
    ports     = ["22"]
  }
  target_tags = ["bastion"]
}
