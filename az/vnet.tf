resource "azurerm_virtual_network" "vnet" {
  name                = var.network_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.my_cidr]
  tags                = var.tags
}

locals {
  # 00.1 - 127.254 = 32766; 128.1 - 191.254 = 16382; 192.1 - 255.254 = 16382
  subnets = cidrsubnets(var.my_cidr, 3, 3, 3, 3, 3)

  bastion_ip = cidrhost(azurerm_subnet.private_sub_servers.address_prefixes[0], 101)
  ldap_ip    = cidrhost(azurerm_subnet.private_sub_servers.address_prefixes[0], 102)

  starburst_ip = cidrhost(azurerm_subnet.private_sub_aks_regular.address_prefixes[0], 103)
}

resource "azurerm_subnet" "private_sub_servers" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name             = "prv_aks_srv"
  address_prefixes = [local.subnets[0]]
}

resource "azurerm_subnet" "private_sub_aks_regular" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name             = "prv_aks_reg"
  address_prefixes = [local.subnets[1]]
}

resource "azurerm_subnet" "private_sub_aks_spot" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name             = "prv_aks_spot"
  address_prefixes = [local.subnets[2]]
}

resource "azurerm_subnet" "db_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name              = "db_sub"
  address_prefixes  = [local.subnets[3]]
  service_endpoints = ["Microsoft.Sql"]
}

resource "azurerm_subnet" "obj_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name              = "obj_sub"
  address_prefixes  = [local.subnets[4]]
  service_endpoints = ["Microsoft.Storage"]
}
