resource "azurerm_virtual_network" "vnet" { 
  name                = "${var.cluster_name}-vpc"
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

  name                 = "private_sub"
  address_prefixes     = [local.subnets[0]]
  enforce_private_link_endpoint_network_policies = true
}

resource "azurerm_subnet" "db_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name                 = "db_sub"
  address_prefixes     = [local.subnets[1]]
  service_endpoints    = ["Microsoft.Sql"]
  enforce_private_link_endpoint_network_policies = true
}

resource "azurerm_subnet" "obj_sub" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name                 = "obj_sub"
  address_prefixes     = [local.subnets[2]]
  service_endpoints    = ["Microsoft.Storage"]
  enforce_private_link_endpoint_network_policies = true
}

data "azurerm_virtual_network" "vpn_vnet" {
  resource_group_name = "vpn"
  name                = "OpenVPNVNet"
}

resource "azurerm_virtual_network_peering" "vpn_to_aks" {
  name                      = "vpn_to_aks"
  resource_group_name       = data.azurerm_virtual_network.vpn_vnet.resource_group_name
  virtual_network_name      = data.azurerm_virtual_network.vpn_vnet.name
  remote_virtual_network_id = azurerm_virtual_network.vnet.id
}

resource "azurerm_virtual_network_peering" "aks_to_vpn" {
  name                      = "aks_to_vpn"
  resource_group_name       = azurerm_resource_group.rg.name
  virtual_network_name      = azurerm_virtual_network.vnet.name
  remote_virtual_network_id = data.azurerm_virtual_network.vpn_vnet.id
}
