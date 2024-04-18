resource "azurerm_private_dns_zone" "private_dns" {
  name                = var.domain
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "vnet_link" {
  name                  = "vnet-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.private_dns.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  tags                  = var.tags
}

resource "azurerm_private_dns_a_record" "bastion_a_record" {
  name                = "bastion"
  zone_name           = azurerm_private_dns_zone.private_dns.name
  resource_group_name = azurerm_resource_group.rg.name
  ttl                 = 3600
  records             = [local.bastion_ip]
  tags                = var.tags
}
