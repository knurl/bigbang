resource "azurerm_storage_account" "storacct" {
  name                     = var.storage_account
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_kind             = "StorageV2"
  account_replication_type = "LRS"
  is_hns_enabled           = "true"
  tags                     = var.tags
}

resource "azurerm_storage_container" "container" {
  name                  = var.bucket_name
  storage_account_name  = azurerm_storage_account.storacct.name
  container_access_type = "private"
}

resource "azurerm_storage_data_lake_gen2_filesystem" "adls_gen2_fs" {
  name               = "adls-gen2-fs"
  storage_account_id = azurerm_storage_account.storacct.id
}

/*
 * TODO: I don't *think* I need to have my own private dns zones and vnet
 * links. I think you only need to create those if you're linking to multiple
 * vnets. However, I tried getting rid of them everywhere (and the
 * private_dns_zone_group entry in the private endpoints) and it failed... the
 * private endpoints were created but DNS was returning a public address for
 * the FQDN given for the private endpoint, which is wrong.
 */
resource "azurerm_private_dns_zone" "prvdns-adls" {
  name                = "privatelink.dfs.core.windows.net"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "dnslink-adls" {
  name                  = "${azurerm_virtual_network.vnet.name}-dnslink-adls"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.prvdns-adls.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  tags                  = var.tags
}

resource "azurerm_private_endpoint" "pe_adls" {
  name                = "${var.storage_account}-pe"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  subnet_id           = azurerm_subnet.obj_sub.id

  private_service_connection {
    name                           = "${var.storage_account}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_storage_account.storacct.id
    subresource_names              = ["dfs"]
  }

  private_dns_zone_group {
    name                 = "${var.storage_account}-dnszg"
    private_dns_zone_ids = [azurerm_private_dns_zone.prvdns-adls.id]
  }

  tags = var.tags
}
