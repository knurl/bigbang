resource "azurerm_synapse_workspace" "synapse_ws" {
  name                = var.synapse_ws_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.adls_gen2_fs.id

  sql_administrator_login          = var.db_user
  sql_administrator_login_password = var.db_password

  tags = var.tags
}

resource "azurerm_synapse_sql_pool" "synapse_sql_pool" {
  name                 = var.synapse_sqlpool_name
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  sku_name             = "DW300c"
  create_mode          = "Default"
}

resource "azurerm_synapse_firewall_rule" "example" {
  name                 = "AllowAllWindowsAzureIps"
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  start_ip_address     = "0.0.0.0"
  end_ip_address       = "0.0.0.0"
}
