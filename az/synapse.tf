resource "azurerm_synapse_workspace" "synapse_ws" {
  name                = var.synapse_ws_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  managed_virtual_network_enabled = true

  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.adls_gen2_fs.id

  sql_administrator_login          = var.db_user
  sql_administrator_login_password = var.db_password

  tags = var.tags
}

resource "azurerm_synapse_sql_pool" "synapse_sql_pool" {
  name                 = var.db_name
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  sku_name             = "DW300c"
  create_mode          = "Default"
  tags                 = var.tags
}

resource "azurerm_synapse_firewall_rule" "example" {
  name                 = "AllowAllWindowsAzureIps"
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  start_ip_address     = "0.0.0.0"
  end_ip_address       = "0.0.0.0"
}

resource "azurerm_synapse_managed_private_endpoint" "synapse_endpoint" {
  name                 = "${var.synapse_ws_name}-pe"
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  target_resource_id   = azurerm_storage_account.storacct.id
  subresource_name     = "dfs"
  depends_on           = [azurerm_synapse_firewall_rule.example]
}
