resource "azurerm_synapse_workspace" "synapse_ws" {
  name                = var.synapse_ws_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.adls_gen2_fs.id

  sql_administrator_login          = var.db_user
  sql_administrator_login_password = var.db_password

  tags = var.tags
}
