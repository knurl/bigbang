data "aws_availability_zones" "available" {}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.10.0"

  name = var.network_name
  cidr = var.my_cidr

  azs              = data.aws_availability_zones.available.names
  private_subnets  = [for k in ["prv_a", "prv_b", "prv_c"] : module.subnet_addrs.network_cidr_blocks[k]]
  database_subnets = [for k in ["db_a", "db_b", "db_c"] : module.subnet_addrs.network_cidr_blocks[k]]
  public_subnets   = [for k in ["pub_a", "pub_b", "pub_c"] : module.subnet_addrs.network_cidr_blocks[k]]
  redshift_subnets = [for k in ["red_a", "red_b", "red_c"] : module.subnet_addrs.network_cidr_blocks[k]]

  create_database_subnet_group = true
  database_subnet_group_name   = "${var.network_name}-sg-db"
  create_redshift_subnet_group = true
  redshift_subnet_group_name   = "${var.network_name}-sg-red"

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

data "aws_iam_policy_document" "vpc_endpoint_policy_doc" {
  statement {
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    effect = "Allow"

    resources = [
      aws_s3_bucket.s3_bucket.arn,
      "${aws_s3_bucket.s3_bucket.arn}/*",
    ]

    condition {
      test     = "ArnEquals"
      variable = "aws:PrincipalArn"
      values   = ["${module.eks.eks_managed_node_groups["ng"].iam_role_arn}"]
    }
  }
}

module "vpc_endpoints" {
  source = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"

  vpc_id             = module.vpc.vpc_id
  security_group_ids = [aws_security_group.vpc_endpoint_sg.id]

  endpoints = {
    s3 = {
      service    = "s3"
      tags       = var.tags
      subnet_ids = module.vpc.private_subnets
      policy     = data.aws_iam_policy_document.vpc_endpoint_policy_doc.json
    }
  }
}

locals {
  bastion_ip   = cidrhost(module.vpc.public_subnets_cidr_blocks[0], 101)
  ldap_ip      = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 102)
  starburst_ip = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 103)
  ranger_ip    = cidrhost(module.vpc.private_subnets_cidr_blocks[0], 104)
}

resource "aws_key_pair" "key_pair" {
  key_name_prefix = "${var.cluster_name}-bastion-key"
  public_key      = var.ssh_public_key
  tags            = var.tags
}

