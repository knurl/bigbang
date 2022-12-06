# Create a security group for our Redshift cluster. It should allow any
# of the worker nodes in our Kubernetes cluster to connect in.
resource "aws_security_group" "redshift_sg" {
  name                   = "redshift_sg"
  vpc_id                 = data.aws_vpc.sb_vpc.id
  revoke_rules_on_delete = true
  count                  = var.disable_slow_sources

  # Any protocol or port, as long as it comes from one of the worker nodes in
  # our Kubernetes cluster, where we'll be running Starburst.
  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [module.eks.node_security_group_id]
  }

  tags = merge(var.tags, { Name = "redshift_sg" })
}

resource "aws_redshift_cluster" "redshift" {
  cluster_identifier = var.redshift_cluster_name
  database_name      = var.db_name
  master_username    = var.db_user
  master_password    = var.db_password
  node_type          = "dc2.large"
  cluster_type       = "multi-node"
  number_of_nodes    = 1
  count              = var.disable_slow_sources

  automated_snapshot_retention_period = 1
  skip_final_snapshot                 = true

  vpc_security_group_ids    = aws_security_group.redshift_sg.*.id
  cluster_subnet_group_name = aws_redshift_subnet_group.redshift_sngrp.id

  tags = merge(var.tags, { Name = var.redshift_cluster_name })
}
