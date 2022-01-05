resource "azurerm_synapse_workspace" "synapse_ws" {
  name                = var.synapse_ws_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  count               = var.disable_slow_sources

  managed_virtual_network_enabled = true

  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.adls_gen2_fs.id

  sql_administrator_login          = var.db_user
  sql_administrator_login_password = var.db_password

  tags = var.tags
}

resource "azurerm_synapse_firewall_rule" "synfw_allow_azure_ips" {
  name                 = "AllowAllWindowsAzureIps"
  synapse_workspace_id = join("", azurerm_synapse_workspace.synapse_ws.*.id)
  start_ip_address     = "0.0.0.0"
  end_ip_address       = "0.0.0.0"
  count                = var.disable_slow_sources
}

resource "azurerm_synapse_sql_pool" "synapse_sql_pool" {
  name                 = var.db_name
  synapse_workspace_id = join("", azurerm_synapse_workspace.synapse_ws.*.id)
  sku_name             = "DW300c"
  create_mode          = "Default"
  tags                 = var.tags
  count                = var.disable_slow_sources

  # FIXME This probably isn't needed strictly, but I've noticed that if we
  # create the private endpoint immediately after creating the firewall rules,
  # it will fail, but if it has a bit more time, then it works. So I'm forcing
  # that here. I'm hoping a future rev of the Azure provider will fix that.
  depends_on = [azurerm_synapse_firewall_rule.synfw_allow_azure_ips]
}

/*
 * TODO: Can't support a private endpoint right now. Terraform struggles to
 * work with the IP filtering the firewall does, and seems to need access from
 * the home IP just to manipulate the infrastructure. A change to the firewall
 * rules isn't sufficient once the firewall rules are set up as during the
 * apply, Terraform needs to read the state of the private endpoint through the
 * firewall, _before_ making changes to the firewall, resulting in failure.
resource "azurerm_synapse_firewall_rule" "synfw_allow_home_ip" {
  name                 = "AllowHomeIp"
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  start_ip_address     = var.my_public_ip
  end_ip_address       = var.my_public_ip
}

resource "azurerm_synapse_managed_private_endpoint" "synapse_endpoint" {
  name                 = "${var.synapse_ws_name}-pe"
  synapse_workspace_id = azurerm_synapse_workspace.synapse_ws.id
  target_resource_id   = azurerm_storage_account.storacct.id
  subresource_name     = "dfs"

  depends_on = [
    azurerm_synapse_firewall_rule.synfw_allow_azure_ips,
    azurerm_synapse_firewall_rule.synfw_allow_home_ip,
    azurerm_synapse_sql_pool.synapse_sql_pool
  ]
}
*/
