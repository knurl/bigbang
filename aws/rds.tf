# Create a security group for our RDS database instances. It should allow any
# of the worker nodes in our Kubernetes cluster to connect in—otherwise we
# won't be able to get Starburst going. It should also include an entry to
# allow connecting in from the VPN subnet (this way we can use the psql or
# mysql client to connect).
resource "aws_security_group" "rds_sg" {
  name                   = "rds_sg"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  # Any protocol or port, as long as it comes from one of the worker nodes in
  # our Kubernetes cluster, where we'll be running Starburst.
  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [module.eks.node_security_group_id]
  }

  tags = merge(var.tags, { Name = "rds_sg" })
}

# Starburst internal - event logger
resource "aws_db_instance" "evtlog" {
  identifier               = var.evtlog_server_name
  engine                   = "postgres"
  allocated_storage        = 20
  instance_class           = var.db_instance_type
  db_name                  = var.db_name_evtlog
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  apply_immediately        = true
  tags                     = merge(var.tags, { Name = var.evtlog_server_name })
}

# Starburst internal - Hive metastore
resource "aws_db_instance" "hmsdb" {
  identifier               = var.hmsdb_server_name
  engine                   = "postgres"
  allocated_storage        = 20
  instance_class           = var.db_instance_type
  db_name                  = var.db_name_hms
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  apply_immediately        = true
  tags                     = merge(var.tags, { Name = var.hmsdb_server_name })
}

# Starburst internal - Cache service
resource "aws_db_instance" "cachesrvdb" {
  identifier               = var.cachesrv_server_name
  engine                   = "postgres"
  allocated_storage        = 20
  instance_class           = var.db_instance_type
  db_name                  = var.db_name_cachesrv
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  apply_immediately        = true
  tags                     = merge(var.tags, { Name = var.cachesrv_server_name })
}

resource "aws_db_instance" "postgres" {
  identifier               = var.postgres_server_name
  engine                   = "postgres"
  engine_version           = var.postgresql_version
  allocated_storage        = 20
  instance_class           = var.db_instance_type
  name                     = var.db_name
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  apply_immediately        = true
  tags                     = merge(var.tags, { Name = var.postgres_server_name })
}

resource "aws_db_instance" "mysql" {
  identifier               = var.mysql_server_name
  engine                   = "mysql"
  engine_version           = var.mysql_version
  allocated_storage        = 20
  instance_class           = var.db_instance_type
  name                     = var.db_name
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  apply_immediately        = true
  tags                     = merge(var.tags, { Name = var.mysql_server_name })
}
