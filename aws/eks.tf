resource "aws_security_group" "apiserver_sg" {
  name                   = "apiserver_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true
  tags                   = merge(var.tags, { Name = "apiserver_sg" })

  /* Allow access from any internal IP (including the worker nodes, and the
     bastion server) to the api server endpoint. */
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = concat(module.vpc.private_subnets_cidr_blocks, module.vpc.public_subnets_cidr_blocks)
  }

  # Allow access on any protocol between members of the control plane.
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = -1
    self      = true
  }

  # Allow any access outward.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = -1
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "worker_sg" {
  name                   = "worker_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  /* Allow communication to any port from the private subnets */
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = -1
    cidr_blocks = concat(module.vpc.private_subnets_cidr_blocks, module.vpc.public_subnets_cidr_blocks)
  }

  /*
   * AWS security groups disallow outbound communication by default, so we have
   * to explictly enable outbound traffic. AWS security groups are also
   * stateful and keep track of "connections" (even for UDP/ICMP), so if you
   * set a rule here the responses will be ignored for inbound, and vice-versa.
   */
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = -1
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "worker_sg" })
}

module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  cluster_name    = var.cluster_name
  cluster_version = "1.19"
  version         = "15.1.0"

  # Where to place the EKS cluster and workers.
  subnets = module.vpc.private_subnets
  vpc_id  = module.vpc.vpc_id

  # Which subnets get to access the private api server endpoint
  cluster_endpoint_private_access_cidrs = concat(module.vpc.private_subnets_cidr_blocks, module.vpc.public_subnets_cidr_blocks)

  /*
   * We want a cluster with a private api server endpoint. That comes with
   * compromises. We can't use manage_aws_auth, because that will try to apply
   * the aws-auth config by connecting to the endpoint, which will fail.
   * Everything in this section is required for the private endpoint.
   */
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = false
  manage_aws_auth                 = false # Can't for private clusters
  cluster_create_security_group   = false
  cluster_security_group_id       = aws_security_group.apiserver_sg.id
  /*
   * The workers by default are allowed to talk to each other (usually
   * facilitated by a recursive reference to their own security group), and
   * to receive communication from the api server private endpoint. To this we
   * want to allow them to be pinged by anyone on the private networks, and for
   * us to be able to ssh into them
   */
  worker_additional_security_group_ids = [aws_security_group.worker_sg.id]

  # Don't need a kubectl physical file; we'll get it as an output var
  write_kubeconfig = false

  worker_groups_launch_template = [
    {
      name                 = "worker-group"
      instance_type        = var.instance_type
      asg_min_size         = var.node_count
      asg_desired_capacity = var.node_count
      asg_max_size         = var.node_count
      key_name             = aws_key_pair.key_pair.key_name
    }
  ]

  workers_additional_policies = [
    "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess",
    "arn:aws:iam::188806360106:policy/EKS-S3-Glue"
  ]

  tags = merge(var.tags, { Name = var.cluster_name })
}

data "aws_eks_cluster" "eks_cluster" {
  name = module.eks.cluster_id
}

data "aws_eks_cluster_auth" "eks_cluster_auth" {
  name = module.eks.cluster_id
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.eks_cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.eks_cluster.certificate_authority.0.data)
  token                  = data.aws_eks_cluster_auth.eks_cluster_auth.token
}
