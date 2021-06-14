resource "aws_security_group" "ldaps_sg" {
  name                   = "ldaps_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  /* Allow communication to port 22 (SSH) from internal IP addresses only */
  ingress {
    from_port   = 0
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = concat(module.vpc.private_subnets_cidr_blocks, module.vpc.public_subnets_cidr_blocks)
  }

  # LDAPS port is 636
  ingress {
    from_port   = 0
    to_port     = 636
    protocol    = "tcp"
    cidr_blocks = concat(module.vpc.private_subnets_cidr_blocks, module.vpc.public_subnets_cidr_blocks)
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
  subnet_id              = module.vpc.private_subnets.0
  private_ip             = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 102)
  key_name               = aws_key_pair.key_pair.key_name
  vpc_security_group_ids = [aws_security_group.ldaps_sg.id]
  user_data              = file(var.ldaps_launch_script)
  tags                   = merge(var.tags, { Name = "${var.ldaps_name}" })
}
