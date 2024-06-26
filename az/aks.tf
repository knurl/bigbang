resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = var.cluster_name

  network_profile {
    network_plugin = "azure"
  }

  private_cluster_enabled = "true"

  identity {
    type = "SystemAssigned"
  }

  default_node_pool {
    name       = "${var.cluster_name}1"
    node_count = var.node_count

    vm_size  = var.instance_types[0]
    max_pods = var.max_pods_per_node

    upgrade_settings {
      max_surge = "10%"
    }

    enable_node_public_ip = false
    vnet_subnet_id        = azurerm_subnet.private_sub_aks.id
    tags                  = var.tags
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "assignment" {
  principal_id         = azurerm_kubernetes_cluster.aks.identity[0].principal_id
  role_definition_name = "Network Contributor"
  scope                = azurerm_virtual_network.vnet.id
}
