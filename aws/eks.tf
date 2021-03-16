module "eks" {
  source                      = "terraform-aws-modules/eks/aws"
  cluster_name                = var.cluster_name
  cluster_version             = "1.19"
  version                     = "13.2.1"
  subnets                     = module.vpc.private_subnets

  tags                        = merge(var.tags, {Name = var.cluster_name})

  vpc_id                      = module.vpc.vpc_id

  worker_groups               = [
    {
      name                    = "worker-group"
      instance_type           = var.instance_type
      asg_min_size            = var.node_count
      asg_desired_capacity    = var.node_count
      asg_max_size            = var.node_count
    }
  ]

  workers_group_defaults      = {
  	root_volume_type          = "gp2"
  }

  workers_additional_policies = [
    "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess",
    "arn:aws:iam::188806360106:policy/EKS-S3-Glue"
  ]
}

data "aws_eks_cluster" "cluster" {
  name = module.eks.cluster_id
}

data "aws_eks_cluster_auth" "cluster" {
  name = module.eks.cluster_id
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority.0.data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}
