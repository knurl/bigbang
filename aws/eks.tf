module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  cluster_name    = var.cluster_name
  cluster_version = "1.29"
  version         = "20.8.5"

  # Where to place the EKS cluster and workers.
  vpc_id                          = module.vpc.vpc_id
  subnet_ids                      = module.vpc.private_subnets
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = false

  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    # Without the CSI driver, the persistent volume will not become available;
    # we also need to provide an additional policy, below
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }

  /* Disabling creation of key in kms, and 'secret cluster encryption', because
   * it requires the creation and attachment of a policy for which I do not
   * have permission.
   * */
  attach_cluster_encryption_policy = false
  cluster_encryption_config        = {}

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

  # Cluster access entry
  # To add the current caller identity as an administrator
  authentication_mode                      = "API_AND_CONFIG_MAP"
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    ng = {
      name         = "${var.cluster_name}-ng"
      min_size     = 0
      max_size     = var.node_count
      desired_size = var.node_count

      lifecycle = {
        create_before_destroy = false
      }

      update_config = {
        max_unavailable = var.node_count
      }

      instance_types = [var.instance_types[0]]
      capacity_type  = "ON_DEMAND"

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

      # This is related to the CSI driver above. This policy allows the CSI
      # driver to access services like EC2 on your behalf
      iam_role_additional_policies = {
        AmazonEBSCSIDriverPolicy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
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
    }
  }

  tags = {
    Name = var.cluster_name
  }
}
