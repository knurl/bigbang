data "aws_availability_zones" "available" {}

data "aws_ec2_instance_type_offering" "avail_az_instance_map" {
  for_each = toset(data.aws_availability_zones.available.names)

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
  azs               = keys(data.aws_ec2_instance_type_offering.avail_az_instance_map)
  eks_azs           = [local.azs[0], local.azs[1]]
  eks_instance_type = data.aws_ec2_instance_type_offering.avail_az_instance_map[local.azs[0]].instance_type
}
