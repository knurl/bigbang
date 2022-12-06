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
  az_map = { for az, details in data.aws_ec2_instance_type_offerings.avail_az_instance_map : az => details.instance_types if length(details.instance_types) != 0 }
  azs    = keys(local.az_map)
}

data "aws_ec2_instance_type_offering" "preferred_instance_map" {
  for_each = toset(local.azs)

  filter {
    name   = "instance-type"
    values = var.instance_types
  }

  filter {
    name   = "location"
    values = [each.value]
  }

  location_type = "availability-zone"

  preferred_instance_types = var.instance_types
}

locals {
  preferred_azs               = keys(data.aws_ec2_instance_type_offering.preferred_instance_map)
  preferred_eks_azs           = [local.preferred_azs[0], local.preferred_azs[1]]
  preferred_nodegroup_az      = local.preferred_azs[0]
  preferred_nodegroup_subnet  = data.aws_subnet.private_subnet[0].id
  preferred_eks_instance_type = data.aws_ec2_instance_type_offering.preferred_instance_map[local.preferred_nodegroup_az].instance_type
}
