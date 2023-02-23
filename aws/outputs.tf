output "k8s_api_server" {
  value = module.eks.cluster_endpoint
}

output "bastion_address" {
  value = aws_eip.bastion_eip.public_ip
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

output "cachesrv_address" {
  value = length(aws_db_instance.cachesrvdb) > 0 ? aws_db_instance.cachesrvdb[0].address : null
}

output "postgres_address" {
  value = length(aws_db_instance.postgres) > 0 ? aws_db_instance.postgres[0].address : null
}

output "mysql_address" {
  value = length(aws_db_instance.mysql) > 0 ? aws_db_instance.mysql[0].address : null
}

output "redshift_address" {
  value = aws_redshift_cluster.redshift.endpoint
}

output "object_address" {
  value = aws_s3_bucket.s3_bucket.bucket_regional_domain_name
}
