module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  cluster_name    = var.cluster_name
  cluster_version = "1.22"
  version         = "18.26.0"

  # Where to place the EKS cluster and workers.
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = false

  cluster_security_group_additional_rules = {
    admin_access = {
      description = "Ingress to K8S API server from bastion"
      cidr_blocks = ["${aws_instance.bastion.private_ip}/32"]
      protocol    = "tcp"
      from_port   = 443
      to_port     = 443
      type        = "ingress"
    }
  }

  eks_managed_node_groups = {
    ng = {
      name         = "${var.cluster_name}-ng"
      min_size     = 0
      max_size     = var.node_count
      desired_size = var.node_count

      instance_types = [local.eks_instance_type]
      capacity_type  = var.capacity_type == "Spot" ? "SPOT" : "ON_DEMAND"

      # Use only the first AZ to avoid transfer costs between AZs
      subnet_ids = [module.vpc.private_subnets[0]]

      security_group_rules = {
        /* By default, eks module does not allow node-to-node communication.
         * Without that communication the Starburst coordinator will not be
         * able to communicate with the Starburst workers. Allow ingress from
         * other worker nodes here, and following rule allows egress to other
         * workers, as well as elsewhere (e.g. for loading container images).
         */
        worker_ingress = {
          description = "Allow ingress from other workers"
          from_port   = 0
          to_port     = 0
          protocol    = -1
          self        = true # only from other workers
          type        = "ingress"
        }

        worker_egress = {
          description = "Allow egress anywhere"
          from_port   = 0
          to_port     = 0
          protocol    = -1
          cidr_blocks = ["0.0.0.0/0"]
          type        = "egress"
        }
      }

      # TODO: IMDSv2 is the default, but doesn't work with our EKS containers.
      # Note that "http_endpoint" is enabled by default, but for some reason
      # Terraform occasionally crashes with an error message saying it's set to
      # '', so I'm setting it explicitly here to avoid that.
      metadata_options = {
        "http_endpoint" : "enabled",
        "http_tokens" : "optional",
        "http_put_response_hop_limit" : 64
      }

      tags = var.tags
    }
  }

  tags = merge(var.tags, { Name = var.cluster_name })
}

resource "aws_iam_policy" "eks_trino_worker_policy" {
  name = "eks-trino-worker-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "cloudformation:*",
          "glue:*",
          "sts:AssumeRole",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:ListSecretVersionIds"
        ]
        Resource = "*"
      }
    ]
  })
  tags = var.tags
}

# Attach policies separately due to Terraform bug https://tinyurl.com/2zj7a42r
resource "aws_iam_role_policy_attachment" "attach_eks_trino_worker" {
  for_each   = module.eks.eks_managed_node_groups
  policy_arn = aws_iam_policy.eks_trino_worker_policy.arn
  role       = each.value.iam_role_name
}

resource "aws_iam_role_policy_attachment" "attach_elb_full_access" {
  for_each   = module.eks.eks_managed_node_groups
  policy_arn = "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess"
  role       = each.value.iam_role_name
}
