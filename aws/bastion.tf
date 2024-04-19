resource "aws_security_group" "bastion_sg" {
  name                   = "${var.bastion_name}-sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  /* Allow communication to port 22 (SSH) from the home IP only, or in the case
   * of a downstream bastion host, also allow from the upstream bastion
   * */
  ingress {
    from_port = 22
    to_port   = 22
    protocol  = "tcp"
    /* Restrict to home IP only normally. For Stargate mode, also allow
     * connects from the private subnet, as we will be directing the remote
     * catalogs to point to the bastion, which will use SSH port-forwarding to
     * connect to the *remote* bastion host */
    cidr_blocks = var.bastion_fw_ingress
  }

  /* This might be an upstream bastion host (in a Stargate formation), in which
   * case allow incoming connections on ports 8444-8445
   */
  ingress {
    from_port   = 8444
    to_port     = 8445
    protocol    = "tcp"
    cidr_blocks = [var.my_cidr]
  }

  ingress {
    from_port   = 8
    to_port     = 0
    protocol    = "icmp"
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
    Name = "${var.bastion_name}-sg"
  }
}

resource "aws_network_interface" "bastion_eni" {
  subnet_id       = module.vpc.public_subnets[0]
  security_groups = [aws_security_group.bastion_sg.id]
  private_ips     = [local.bastion_ip]

  tags = {
    Name = "${var.bastion_name}-eni"
  }
}

/*
 * When referring to the public IP address of this bastion, we should instead
 * refer to the EIP's address (see below) and not use public_ip as this field
 * will change after the EIP is attached.
 */
resource "aws_instance" "bastion" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.small_instance_type
  key_name      = aws_key_pair.key_pair.key_name

  network_interface {
    network_interface_id = aws_network_interface.bastion_eni.id
    device_index         = 0
  }

  tags = {
    Name = "${var.bastion_name}"
  }

  /* We have a dependency on our NAT gateway for outbound connectivity during
   * our launch script, as well as DNS so that certificates can be validated.
   */
  depends_on = [module.vpc, aws_route53_record.bastion_a_record]
}

resource "aws_eip" "bastion_eip" {
  domain                    = "vpc"
  instance                  = aws_instance.bastion.id
  associate_with_private_ip = aws_instance.bastion.private_ip
  depends_on                = [module.vpc, aws_instance.bastion]

  tags = {
    Name = "${var.network_name}-bastion-eip"
  }
}
