data "aws_ami" "ubuntu" {
    most_recent = true
    filter {
        name    = "name"
        values  = ["ubuntu/images/hvm-ssd/ubuntu-xenial-16.04-amd64-server-*"]
    }
    filter {
        name    = "virtualization-type"
        values  = ["hvm"]
    }
    owners      = ["099720109477"] # Canonical
}

resource "aws_key_pair" "key_pair" {
  key_name_prefix = "${var.cluster_name}-bastion-key"
  public_key      = var.ssh_public_key
  tags            = var.tags
}

resource "aws_security_group" "bastion_sg" {
  name                   = "bastion_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  /* Allow communication to port 22 (SSH) from anywhere. */
  ingress {
    from_port            = 22
    to_port              = 22
    protocol             = "tcp"
    cidr_blocks          = ["${var.my_public_ip}/32"] # Restrict to home IP only
  }

  ingress {
    from_port            = 22
    to_port              = 22
    protocol             = "tcp"
    cidr_blocks          = ["172.16.0.0/12"]
  }

  tags                   = merge(var.tags, {Name = "bastion_sg"})
}

resource "aws_instance" "bastion" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.bastion_instance_type
  subnet_id              = module.vpc.private_subnets.0
  private_ip             = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 102)
  key_name               = aws_key_pair.key_pair.key_name
  vpc_security_group_ids = [aws_security_group.bastion_sg.id]
  tags                   = merge(var.tags, {Name = "${var.cluster_name}-bastion"})
}
