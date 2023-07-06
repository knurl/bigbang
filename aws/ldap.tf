resource "aws_security_group" "ldaps_sg" {
  name                   = "${var.ldaps_name}-sg"
  vpc_id                 = data.aws_vpc.sb_vpc.id
  revoke_rules_on_delete = true

  /* Allow communication to port 22 (SSH) from internal IP addresses only */
  ingress {
    from_port   = 0
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = local.prvpub_subnet_cidrs
  }

  # LDAPS port is 636
  ingress {
    from_port   = 0
    to_port     = 636
    protocol    = "tcp"
    cidr_blocks = local.prvpub_subnet_cidrs
  }

  /*
   * AWS security groups disallow outbound communication by default, so we have
   * to explictly enable outbound traffic. AWS security groups are also
   * stateful and keep track of "connections" (even for UDP/ICMP), so if you
   * set a rule here the responses will be ignored for inbound, and vice-versa.
   */
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = -1
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.ldaps_name}-sg"
  }
}

resource "aws_network_interface" "ldap_eni" {
  subnet_id       = data.aws_subnet.private_subnet[0].id
  security_groups = [aws_security_group.ldaps_sg.id]

  tags = {
    Name = "${var.ldaps_name}-eni"
  }
}

resource "aws_instance" "ldaps" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.small_instance_type
  key_name      = aws_key_pair.key_pair.key_name
  user_data     = file(var.ldaps_launch_script)

  network_interface {
    network_interface_id = aws_network_interface.ldap_eni.id
    device_index         = 0
  }

  tags = {
    Name = "${var.ldaps_name}"
  }

  /* We have a dependency on DNS so that certificates can be validated. */
  depends_on = [aws_route53_record.ldap_a_record]
}
