resource "aws_security_group" "bastion_sg" {
  name                   = "bastion_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  /* Allow communication to port 22 (SSH) from the home IP only */
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.my_public_ip}/32"] # Restrict to home IP...
  }

  ingress {
    from_port   = 8
    to_port     = 0
    protocol    = "icmp"
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

  tags = merge(var.tags, { Name = "bastion_sg" })
}

resource "aws_instance" "bastion" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.small_instance_type
  subnet_id              = module.vpc.public_subnets.0
  private_ip             = cidrhost(module.vpc.public_subnets_cidr_blocks[0], 101)
  key_name               = aws_key_pair.key_pair.key_name
  vpc_security_group_ids = [aws_security_group.bastion_sg.id]
  tags                   = merge(var.tags, { Name = "${var.bastion_name}" })
}
