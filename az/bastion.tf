resource "azurerm_public_ip" "bastion_pip" {
  name                = "${var.network_name}-bastion-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
}

resource "azurerm_network_interface" "bastion_nic" {
  name                = "${var.network_name}-bastion-nic1"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.private_sub_servers.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.bastion_ip
    public_ip_address_id          = azurerm_public_ip.bastion_pip.id
  }

  tags = var.tags
}

resource "azurerm_linux_virtual_machine" "bastion" {
  name                            = var.bastion_name
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
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }

  tags = var.tags

  /* We don't need a dependency on a NAT here, since Azure doesn't have one; by
   * default a VNET can always route to the Internet. But we do need a
   * dependency on DNS being set up in order for certificates to work */
  depends_on = [azurerm_private_dns_a_record.bastion_a_record]
}

resource "azurerm_network_security_group" "sg_bastion" {
  name                = "${var.network_name}-nsg-bastion"
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

