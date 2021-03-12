output "kubectl_config" {
  value = azurerm_kubernetes_cluster.k8s.kube_config_raw
}

output "evtlog_address" {
  value = azurerm_postgresql_server.evtlog.fqdn
}

output "postgres_address" {
  value = azurerm_postgresql_server.postgres.fqdn
}

output "mariadb_address" {
  value = azurerm_mariadb_server.mariadb.fqdn
}

output "adls_address" {
  value = azurerm_storage_account.storacct.primary_dfs_host
}

output "adls_access_key" {
  value = azurerm_storage_account.storacct.primary_access_key
}

output "private_dns_address" {
  value = azurerm_linux_virtual_machine.dnsfwd.private_ip_address
}
