output "k8s_api_server" {
  value = module.eks.cluster_endpoint
}

output "bastion_address" {
  value = aws_eip.bastion_eip.public_ip
}

output "zone_id" {
  value = aws_route53_zone.private_dns.zone_id
}
