resource "azurerm_network_interface" "bastion-nic" {
  name                            = "bastion-nic"
  location                        = azurerm_resource_group.rg.location
  resource_group_name             = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.private_sub.id
    private_ip_address_allocation = "Static"
    private_ip_address            = cidrhost(azurerm_subnet.private_sub.address_prefixes[0], 102)
  }

  tags = var.tags
}

resource "azurerm_linux_virtual_machine" "bastion" {
  name                   = "bastion"
  location               = azurerm_resource_group.rg.location
  resource_group_name    = azurerm_resource_group.rg.name
  size                   = var.bastion_instance_type
  admin_username         = "adminuser"
  network_interface_ids  = [azurerm_network_interface.bastion-nic.id]
  disable_password_authentication = true

  admin_ssh_key {
    username             = "adminuser"
    public_key           = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher            = "Canonical"
    offer                = "UbuntuServer"
    sku                  = "16.04-LTS"
    version              = "latest"
  }

  tags                   = var.tags
}
