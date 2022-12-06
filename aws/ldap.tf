resource "aws_security_group" "ldaps_sg" {
  name                   = "ldaps_sg"
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

  tags = merge(var.tags, { Name = "ldaps_sg" })
}

resource "aws_instance" "ldaps" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.small_instance_type
  subnet_id              = data.aws_subnet.private_subnet[0].id
  private_ip             = local.ldap_ip
  key_name               = aws_key_pair.key_pair.key_name
  vpc_security_group_ids = [aws_security_group.ldaps_sg.id]
  user_data              = file(var.ldaps_launch_script)
  tags                   = merge(var.tags, { Name = "${var.ldaps_name}" })

  /* We have a dependency on DNS so that certificates can be validated. */
  depends_on = [aws_route53_record.ldap_a_record]
}
