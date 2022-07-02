data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_ec2_instance_type_offerings" "avail_az_instance_map" {
  for_each = toset(data.aws_availability_zones.available.names)

  filter {
    name   = "instance-type"
    values = var.instance_types
  }

  filter {
    name   = "location"
    values = ["${each.key}"]
  }

  location_type = "availability-zone"
}

locals {
  az_map            = { for az, details in data.aws_ec2_instance_type_offerings.avail_az_instance_map : az => details.instance_types if length(details.instance_types) != 0 }
  azs               = keys(local.az_map)
  eks_azs           = [local.azs[0], local.azs[1]]
  nodegroup_az      = local.azs[0]
  eks_instance_type = local.az_map[local.nodegroup_az][0]
}
