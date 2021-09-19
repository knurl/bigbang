resource "azurerm_public_ip" "bastion_pip" {
  name                = "bastion-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Dynamic"
}

resource "azurerm_network_interface" "bastion_nic" {
  name                = "bastion-nic1"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.private_sub.id
    private_ip_address_allocation = "Static"
    private_ip_address            = cidrhost(azurerm_subnet.private_sub.address_prefixes[0], 101)
    public_ip_address_id          = azurerm_public_ip.bastion_pip.id
  }

  tags = var.tags
}

resource "azurerm_linux_virtual_machine" "bastion" {
  name                            = "bastion"
  location                        = azurerm_resource_group.rg.location
  resource_group_name             = azurerm_resource_group.rg.name
  size                            = var.small_instance_type
  admin_username                  = "ubuntu"
  network_interface_ids           = [azurerm_network_interface.bastion_nic.id]
  disable_password_authentication = true

  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "18.04-LTS"
    version   = "latest"
  }

  tags = var.tags
}

resource "azurerm_network_security_group" "sg_bastion" {
  name                = "sg-bastion"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  security_rule {
    access            = "Allow"
    direction         = "Inbound"
    name              = "allow-ssh"
    priority          = 100
    protocol          = "Tcp"
    source_port_range = "*"
    /* Restrict to home IP only normally. For Stargate mode, also allow
     * connects from the private subnet, as we will be directing the remote
     * catalogs to point to the bastion, which will use SSH port-forwarding to
     * connect to the *remote* bastion host */
    source_address_prefixes = var.bastion_fw_ingress
    destination_port_range  = "22"
    /*
     * From Microsoft's online docs: "If you specify an address for an Azure
     * resource, specify the private IP address assigned to the resource.
     * Network security groups are processed after Azure translates a public IP
     * address to a private IP address for inbound traffic...
     */
    destination_address_prefix = azurerm_linux_virtual_machine.bastion.private_ip_address
  }
}

resource "azurerm_network_interface_security_group_association" "bastion_sga" {
  network_interface_id      = azurerm_network_interface.bastion_nic.id
  network_security_group_id = azurerm_network_security_group.sg_bastion.id
}

