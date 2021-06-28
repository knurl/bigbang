data "aws_availability_zones" "available" {}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.2.0"

  name = var.network_name
  cidr = var.my_cidr

  create_database_subnet_group = true
  database_subnet_group_name   = "${var.network_name}-sg-db"

  azs              = data.aws_availability_zones.available.names
  private_subnets  = [for k in ["prv_a", "prv_b", "prv_c"] : module.subnet_addrs.network_cidr_blocks[k]]
  public_subnets   = [for k in ["pub_a", "pub_b", "pub_c"] : module.subnet_addrs.network_cidr_blocks[k]]
  database_subnets = [for k in ["db_a", "db_b", "db_c"] : module.subnet_addrs.network_cidr_blocks[k]]

  /*
   * We are setting up a fully-private EKS cluster on this VPC, which
   * automatically creates a Route 53 private hosted zone and associates it
   * with this VPC. To make that work, we need to have the following settings.
   * (We also need to use Amazon provided-DNS, but that is the default.)
   */
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Our workers will need to be able to get packages
  enable_nat_gateway = true
  single_nat_gateway = true

  # Required to allow ELBs on the private subnets
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }

  tags = var.tags
}

resource "aws_key_pair" "key_pair" {
  key_name_prefix = "${var.cluster_name}-bastion-key"
  public_key      = var.ssh_public_key
  tags            = var.tags
}

