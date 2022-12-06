data "aws_vpcs" "starburst_vpcs" {
  tags = {
    team        = "edu"
    org         = "enablement"
    cloud       = "aws"
    project     = "training"
    environment = "training"
    Name        = "bootcamp-vpc"
    user        = "sa.training"
  }
}

locals {
  vpc_id = data.aws_vpcs.starburst_vpcs.ids[0]
}

data "aws_vpc" "sb_vpc" {
  id = local.vpc_id
}

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_subnet" "public_subnet" {
  count             = length(data.aws_availability_zones.available.names)
  vpc_id            = data.aws_vpc.sb_vpc.id
  availability_zone = data.aws_availability_zones.available.names[count.index]

  filter {
    name   = "tag:Name"
    values = ["pub-${data.aws_availability_zones.available.names[count.index]}"]
  }
}

data "aws_subnet" "private_subnet" {
  count             = length(data.aws_availability_zones.available.names)
  vpc_id            = data.aws_vpc.sb_vpc.id
  availability_zone = data.aws_availability_zones.available.names[count.index]

  filter {
    name   = "tag:Name"
    values = ["default-pri-${data.aws_availability_zones.available.names[count.index]}"]
  }
}

resource "aws_ec2_tag" "stag_for_ilb_1" {
  count       = length(data.aws_availability_zones.available.names)
  resource_id = data.aws_subnet.private_subnet[count.index].id
  key         = "kubernetes.io/cluster/${var.cluster_name}"
  value       = "shared"
}

resource "aws_ec2_tag" "stag_for_ilb_2" {
  count       = length(data.aws_availability_zones.available.names)
  resource_id = data.aws_subnet.private_subnet[count.index].id
  key         = "kubernetes.io/role/internal-elb"
  value       = "1"
}

data "aws_db_subnet_group" "database_sngrp" {
  name = "private"
}

resource "aws_redshift_subnet_group" "redshift_sngrp" {
  name       = "${var.network_name}-sg-red"
  subnet_ids = local.prv_subnet_ids
  tags       = var.tags
}

locals {
  bastion_ip          = cidrhost(data.aws_subnet.public_subnet[0].cidr_block, 101)
  ldap_ip             = cidrhost(data.aws_subnet.private_subnet[0].cidr_block, 102)
  starburst_ip        = cidrhost(data.aws_subnet.private_subnet[0].cidr_block, 103)
  prv_subnet_ids      = data.aws_subnet.private_subnet.*.id
  pub_subnet_ids      = data.aws_subnet.public_subnet.*.id
  prv_subnet_cidrs    = data.aws_subnet.private_subnet.*.cidr_block
  pub_subnet_cidrs    = data.aws_subnet.public_subnet.*.cidr_block
  prvpub_subnet_cidrs = concat(local.pub_subnet_cidrs, local.prv_subnet_cidrs)
}

resource "aws_key_pair" "key_pair" {
  key_name_prefix = "${var.cluster_name}-bastion-key"
  public_key      = var.ssh_public_key
  tags            = var.tags
}
