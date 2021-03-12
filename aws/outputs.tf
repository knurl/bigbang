output "kubectl_config" {
  value = module.eks.kubeconfig
}

output "evtlog_address" {
  value = aws_db_instance.evtlog.address
}

output "postgres_address" {
  value = aws_db_instance.postgres.address
}

output "mariadb_address" {
  value = aws_db_instance.mariadb.address
}
