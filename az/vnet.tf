resource "azurerm_virtual_network" "vnet" {
  name                = var.network_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.my_cidr]
  tags                = var.tags
}

locals {
  # 00.1 - 127.254 = 32766; 128.1 - 191.254 = 16382; 192.1 - 255.254 = 16382
  subnets = cidrsubnets(var.my_cidr, 1, 2, 2)
}

resource "azurerm_subnet" "private_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name                                           = "private_sub"
  address_prefixes                               = [local.subnets[0]]
  enforce_private_link_endpoint_network_policies = true
}

resource "azurerm_subnet" "db_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name                                           = "db_sub"
  address_prefixes                               = [local.subnets[1]]
  service_endpoints                              = ["Microsoft.Sql"]
  enforce_private_link_endpoint_network_policies = true
}

resource "azurerm_subnet" "obj_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name                                           = "obj_sub"
  address_prefixes                               = [local.subnets[2]]
  service_endpoints                              = ["Microsoft.Storage"]
  enforce_private_link_endpoint_network_policies = true
}
