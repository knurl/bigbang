resource "azurerm_private_dns_zone" "private_dns" {
  name                = "az.starburstdata.net"
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
  records             = [azurerm_linux_virtual_machine.bastion.private_ip_address]
  tags                = var.tags
}

resource "azurerm_private_dns_a_record" "ldap_a_record" {
  name                = "ldap"
  zone_name           = azurerm_private_dns_zone.private_dns.name
  resource_group_name = azurerm_resource_group.rg.name
  ttl                 = 3600
  records             = [azurerm_linux_virtual_machine.ldaps.private_ip_address]
  tags                = var.tags
}

resource "azurerm_private_dns_a_record" "starburst_a_record" {
  name                = "starburst"
  zone_name           = azurerm_private_dns_zone.private_dns.name
  resource_group_name = azurerm_resource_group.rg.name
  ttl                 = 3600
  records             = [var.upstream_stargate ? azurerm_linux_virtual_machine.bastion.private_ip_address : local.starburst_ip]
  tags                = var.tags
}
