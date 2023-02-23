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
    name       = "${var.cluster_name}np"
    node_count = 1

    vm_size  = var.instance_types[0]
    max_pods = var.max_pods_per_node

    enable_node_public_ip = false
    vnet_subnet_id        = azurerm_subnet.private_sub_aks_regular.id
    tags                  = var.tags
  }

  tags = var.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "secondary" {
  name                  = "${var.cluster_name}nps"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id

  #
  # compute
  #
  node_count = var.node_count - 1 # we have 1 in default node group
  vm_size    = var.instance_types[0]
  max_pods   = var.max_pods_per_node * var.node_count

  # Instrumentation for spot instances
  priority       = var.capacity_type == "Spot" ? "Spot" : "Regular"
  spot_max_price = -1 # allow any price up to 
  node_labels    = { "kubernetes.azure.com/scalesetpriority" = "spot" }
  node_taints    = ["kubernetes.azure.com/scalesetpriority=spot:NoSchedule"]

  #
  # network
  #
  enable_node_public_ip = false
  vnet_subnet_id        = azurerm_subnet.private_sub_aks_spot.id

  tags = var.tags
}

resource "azurerm_role_assignment" "assignment" {
  principal_id         = azurerm_kubernetes_cluster.aks.identity[0].principal_id
  role_definition_name = "Network Contributor"
  scope                = azurerm_virtual_network.vnet.id
}
