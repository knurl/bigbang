output "bastion_address" {
  value = azurerm_linux_virtual_machine.bastion.private_ip_address
}

output "evtlog_address" {
  value = azurerm_postgresql_server.evtlog.fqdn
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
  value = azurerm_storage_account.storacct.primary_access_key
}

output "private_dns_address" {
  value = azurerm_linux_virtual_machine.dnsfwd.private_ip_address
}
