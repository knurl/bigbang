data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.7.1"

  name = var.network_name
  cidr = var.my_cidr

  azs             = data.aws_availability_zones.available.names
  private_subnets = [for k, v in local.azs : cidrsubnet(var.my_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.my_cidr, 8, k + 48)]

  /*
   * We are setting up a fully-private EKS cluster on this VPC, which
   * automatically creates a Route 53 private hosted zone and associates it
   * with this VPC. To make that work, we need to have the following settings.
   * (We also need to use Amazon provided-DNS, but that is the default.)
   */
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Our workers will need to be able to get packages
  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true

  # Required to allow internal ELBs
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }

  tags = var.tags
}

resource "aws_security_group" "vpc_endpoint_sg" {
  name                   = "vpc_endpoint_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  # Any protocol or port, as long as it comes from one of the worker nodes in
  # our Kubernetes cluster, where we'll be running Starburst.
  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [module.eks.node_security_group_id]
  }
}

locals {
  azs                 = slice(data.aws_availability_zones.available.names, 0, 3)
  bastion_ip          = cidrhost(module.vpc.public_subnets_cidr_blocks[0], 101)
  client_ip           = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 101)
  prvpub_subnet_cidrs = concat(module.vpc.public_subnets_cidr_blocks, module.vpc.private_subnets_cidr_blocks)
}

resource "aws_key_pair" "key_pair" {
  key_name_prefix = "${var.cluster_name}-bastion-key"
  public_key      = var.ssh_public_key
}

module "vpc_endpoints" {
  source = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"

  vpc_id = module.vpc.vpc_id

  create_security_group      = true
  security_group_name_prefix = "${var.network_name}-vpcep-"
  security_group_description = "VPC endpoint security group"
  security_group_rules = {
    ingress_https = {
      description = "HTTPS from VPC"
      cidr_blocks = [module.vpc.vpc_cidr_block]
    }
  }

  endpoints = {
    eks = {
      service             = "eks"
      private_dns_enabled = true
      dns_options = {
        private_dns_only_for_inbound_resolver_endpoint = false
      }
      subnet_ids = module.vpc.private_subnets
    }
  }

  tags = var.tags
}
