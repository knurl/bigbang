output "k8s_api_server" {
  value = azurerm_kubernetes_cluster.aks.private_fqdn
}

output "bastion_address" {
  value = azurerm_linux_virtual_machine.bastion.public_ip_address
}

output "ldaps_address" {
  value = azurerm_linux_virtual_machine.ldaps.private_ip_address
}

output "starburst_address" {
  value = local.starburst_address
}

output "ranger_address" {
  value = local.ranger_address
}

output "evtlog_address" {
  value = azurerm_postgresql_server.postgres.fqdn
}

output "postgres_address" {
  value = azurerm_postgresql_server.postgres.fqdn
}

output "mysql_address" {
  value = azurerm_mysql_server.mysql.fqdn
}

output "object_address" {
  value = azurerm_storage_account.storacct.primary_dfs_host
}

output "object_key" {
  value     = azurerm_storage_account.storacct.primary_access_key
  sensitive = true
}

output "synapse_address" {
  value = azurerm_synapse_workspace.synapse_ws.connectivity_endpoints["sql"]
}
