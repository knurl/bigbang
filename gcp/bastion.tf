resource "google_compute_address" "bastion_ip" {
  project      = data.google_project.project.project_id
  region       = var.region
  name         = "${var.network_name}-bastion-eip"
  address_type = "EXTERNAL"
}

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
    network_ip = local.bastion_address
    access_config {
      nat_ip = google_compute_address.bastion_ip.address
    }
  }

  metadata = {
    ssh-keys = "ubuntu:${var.ssh_public_key}"
  }

  # Make sure sshguard never blocks the home IP
  metadata_startup_script = "echo ${var.my_public_ip} >> /etc/sshguard/whitelist && /etc/init.d/sshguard restart"
  labels                  = var.tags

  /* We have a dependency on our NAT gateway for outbound connectivity during
   * our launch script, as well as DNS so that certificates can be validated.
   */
  depends_on = [google_compute_router_nat.nat, google_dns_record_set.bastion_a_record]
}

resource "google_compute_firewall" "fw-bastion" {
  name    = "${var.bastion_name}-fw"
  network = resource.google_compute_network.vpc.self_link
  project = data.google_project.project.project_id
  /* Restrict to home IP only normally. For Stargate mode, also allow connects
   * from the private subnet, as we will be directing the remote catalogs to
   * point to the bastion, which will use SSH port-forwarding to connect to the
   * *remote* bastion host */
  source_ranges = var.bastion_fw_ingress
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  target_tags = ["bastion"]
}
