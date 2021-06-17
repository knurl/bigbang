output "k8s_api_server" {
  value = module.eks.cluster_endpoint
}

output "bastion_address" {
  value = aws_instance.bastion.public_ip
}

output "ldaps_address" {
  value = aws_instance.ldaps.private_ip
}

output "route53_zone_id" {
  value = aws_route53_zone.private_dns.zone_id
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
  value     = module.eks.kubeconfig
  sensitive = true
}

output "worker_iam_role_arn" {
  value = module.eks.worker_iam_role_arn
}
