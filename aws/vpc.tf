data "aws_availability_zones" "available" {}

module "vpc" {
  source               = "terraform-aws-modules/vpc/aws"
  version              = "2.71.0"

  name                 = "${var.cluster_name}-vpc"
  cidr                 = var.my_cidr

  create_database_subnet_group = true
  azs                  = data.aws_availability_zones.available.names
  private_subnets      = [for k in ["prv_a", "prv_b", "prv_c"]: module.subnet_addrs.network_cidr_blocks[k]]
  public_subnets       = [for k in ["pub_a", "pub_b", "pub_c"]: module.subnet_addrs.network_cidr_blocks[k]]
  database_subnets     = [for k in ["db_a", "db_b", "db_c"]: module.subnet_addrs.network_cidr_blocks[k]]

  enable_dns_hostnames = true
  enable_dns_support   = true

  enable_nat_gateway   = true
  single_nat_gateway   = true

  tags                 = merge(var.tags, {Name = module.vpc.name})

  # Required to allow ELBs on the private subnets
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"               = "1"
  }
}

data "aws_instance" "i_vpn" {
  instance_id = var.vpn_instance_id
}

data "aws_subnet" "sn_ingress" {
  id = data.aws_instance.i_vpn.subnet_id
}

data "aws_route_table" "rt_ingress" {
  subnet_id = data.aws_instance.i_vpn.subnet_id
}

resource "aws_vpc_peering_connection" "vpc_peer" {
  peer_vpc_id = data.aws_subnet.sn_ingress.vpc_id
  vpc_id      = module.vpc.vpc_id
  auto_accept = true
  tags        = merge(var.tags, {Name = "vpc_peer"})

  accepter {
    allow_remote_vpc_dns_resolution = true
  }

  requester {
    allow_remote_vpc_dns_resolution = true
  }
}

resource "aws_route" "rtr_ingress" {
  route_table_id            = data.aws_route_table.rt_ingress.route_table_id
  destination_cidr_block    = var.my_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.vpc_peer.id
}

resource "aws_route" "route_from_eks_vpc" {
  route_table_id            = module.vpc.private_route_table_ids[0]
  destination_cidr_block    = data.aws_subnet.sn_ingress.cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.vpc_peer.id
}
