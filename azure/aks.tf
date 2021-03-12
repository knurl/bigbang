resource "azurerm_kubernetes_cluster" "k8s" {
  name                        = var.cluster_name
  location                    = azurerm_resource_group.rg.location
  resource_group_name         = azurerm_resource_group.rg.name
  dns_prefix                  = var.cluster_name

  network_profile {
    network_plugin            = "azure"
  }

  private_cluster_enabled     = "true"
  identity {
    type                      = "SystemAssigned"
  }

  default_node_pool {
    name                      = "default"
    node_count                = var.node_count
    vm_size                   = var.instance_type
    enable_node_public_ip     = false
    vnet_subnet_id            = azurerm_subnet.private_sub.id
    tags                      = var.tags
    max_pods                  = 32
  }

  addon_profile {
    kube_dashboard {
      enabled                 = true
    }
  }

  tags                        = var.tags
}

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.default.kube_config.0.host
  username               = azurerm_kubernetes_cluster.default.kube_config.0.username
  password               = azurerm_kubernetes_cluster.default.kube_config.0.password
  client_certificate     = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.cluster_ca_certificate)
}
