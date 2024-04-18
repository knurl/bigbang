output "k8s_api_server" {
  value = azurerm_kubernetes_cluster.aks.private_fqdn
}

output "bastion_address" {
  value = azurerm_linux_virtual_machine.bastion.public_ip_address
}

output "zone_id" {
  value = azurerm_private_dns_zone.private_dns.name
}
