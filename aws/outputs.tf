output "bastion_address" {
  value = aws_instance.bastion.private_ip
}

output "evtlog_address" {
  value = aws_db_instance.evtlog.address
}

output "postgres_address" {
  value = aws_db_instance.postgres.address
}

output "mysql_address" {
  value = aws_db_instance.mysql.address
}

output "object_address" {
  value = aws_s3_bucket.s3_bucket.bucket_regional_domain_name
}

output "kubectl_config" {
  value = module.eks.kubeconfig
  sensitive = true
}
