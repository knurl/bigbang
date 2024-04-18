resource "azurerm_virtual_network" "vnet" {
  name                = var.network_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.my_cidr]
  tags                = var.tags
}

locals {
  # 00.1 - 127.254 = 32766; 128.1 - 191.254 = 16382; 192.1 - 255.254 = 16382
  subnets    = cidrsubnets(var.my_cidr, 3, 3, 3, 3, 3)
  bastion_ip = cidrhost(azurerm_subnet.private_sub_servers.address_prefixes[0], 101)
}

resource "azurerm_subnet" "private_sub_servers" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name             = "${var.network_name}-prv_aks_srv"
  address_prefixes = [local.subnets[0]]
}

resource "azurerm_subnet" "private_sub_aks" {
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name

  name             = "${var.network_name}-prv_aks"
  address_prefixes = [local.subnets[1]]
}
