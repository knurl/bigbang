resource "google_compute_instance" "bastion" {
  name         = var.bastion_name
  machine_type = var.small_instance_type
  zone         = var.zone
  project      = data.google_project.project.project_id
  tags         = ["bastion"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.snet.self_link
    network_ip = cidrhost(local.subnetwork_cidr, 101)
    access_config {
      # Empty list => assign ephemeral external IP
    }
  }

  metadata = {
    ssh-keys = "ubuntu:${var.ssh_public_key}"
  }

  # Make sure sshguard never blocks the home IP
  metadata_startup_script = "echo ${var.my_public_ip} >> /etc/sshguard/whitelist && /etc/init.d/sshguard restart"
  labels                  = var.tags
}

resource "google_compute_firewall" "fw-bastion" {
  name    = "fw-${var.bastion_name}"
  network = resource.google_compute_network.vpc.self_link
  project = data.google_project.project.project_id
  # Restrict to home IP or private IPs
  source_ranges = ["${var.my_public_ip}/32", var.my_cidr]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  target_tags = ["bastion"]
}
