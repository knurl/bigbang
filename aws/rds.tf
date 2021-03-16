# Create a security group for our RDS database instances. It should allow any of
# the worker nodes in our Kubernetes cluster to connect in—otherwise we won't be
# able to get Presto going. It should also include an entry to allow connecting
# in from the VPN subnet (this way we can use the psql or mysql client to
# connect). 
resource "aws_security_group" "rds_sg" {
  name                   = "rds_sg"
  vpc_id                 = module.vpc.vpc_id
  tags                   = merge(var.tags, {Name = "rds_sg"})
  revoke_rules_on_delete = true

  # Any protocol or port, as long as it comes from the VPN's subnet (which are
  # private addresses). Generally this will be the way users connect in through
  # the VPN, from home.
  ingress {
    from_port            = 0
    to_port              = 0
    protocol             = "-1"
    cidr_blocks          = [data.aws_subnet.sn_ingress.cidr_block]
  }

  # Any protocol or port, as long as it comes from one of the worker nodes in
  # our Kubernetes cluster, where we'll be running Presto.
  ingress {
    from_port            = 0
    to_port              = 0
    protocol             = "-1"
    cidr_blocks          = module.vpc.private_subnets_cidr_blocks
  }
}

# for the event logger
resource "aws_db_instance" "evtlog" {
  identifier               = var.evtlog_server_name
  engine                   = "postgres"
  allocated_storage        = 20
  instance_class           = "db.m5.xlarge"
  name                     = var.db_name_el
  username                 = var.db_user
  password                 = var.db_password
  skip_final_snapshot      = true
  delete_automated_backups = true
  db_subnet_group_name     = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  tags                     = merge(var.tags, {Name = var.evtlog_server_name})
}

resource "aws_db_instance" "postgres" {
  identifier               = var.postgres_server_name
  engine               		 = "postgres"
  allocated_storage    		 = 20
  instance_class       		 = "db.m5.xlarge"
  name                 		 = var.db_name
  username             		 = var.db_user
  password             		 = var.db_password
  skip_final_snapshot  		 = true
  delete_automated_backups = true
  db_subnet_group_name 		 = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  tags                     = merge(var.tags, {Name = var.postgres_server_name})
}

resource "aws_db_instance" "mariadb" {
  identifier               = var.mariadb_server_name
  engine               		 = "mariadb"
  allocated_storage    		 = 20
  instance_class       		 = "db.m5.xlarge"
  name                 		 = var.db_name
  username             		 = var.db_user
  password             		 = var.db_password
  skip_final_snapshot  		 = true
  delete_automated_backups = true
  db_subnet_group_name 		 = module.vpc.database_subnet_group
  vpc_security_group_ids   = [aws_security_group.rds_sg.id]
  tags                     = merge(var.tags, {Name = var.mariadb_server_name})
}
