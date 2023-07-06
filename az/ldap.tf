resource "azurerm_network_interface" "ldaps_nic" {
  name                = "${var.network_name}-ldaps-nic1"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.private_sub_servers.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.ldap_ip
  }

  tags = var.tags
}

resource "azurerm_linux_virtual_machine" "ldaps" {
  name                            = var.ldaps_name
  location                        = azurerm_resource_group.rg.location
  resource_group_name             = azurerm_resource_group.rg.name
  size                            = var.small_instance_type
  admin_username                  = "ubuntu"
  network_interface_ids           = [azurerm_network_interface.ldaps_nic.id]
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

  /* We don't need a dependency on a NAT here, since Azure doesn't have one; by
   * default a VNET can always route to the Internet. But we do need a
   * dependency on DNS being set up in order for certificates to work */
  depends_on = [azurerm_private_dns_a_record.ldap_a_record]
}

resource "azurerm_network_security_group" "sg_ldaps" {
  name                = "${var.network_name}-nsg-ldaps"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  security_rule {
    access                 = "Allow"
    direction              = "Inbound"
    name                   = "allow-ssh"
    priority               = 100
    protocol               = "Tcp"
    source_port_range      = "*"
    source_address_prefix  = var.my_public_ip
    destination_port_range = "22"
    /*
     * From Microsoft's online docs: "If you specify an address for an Azure
     * resource, specify the private IP address assigned to the resource.
     * Network security groups are processed after Azure translates a public IP
     * address to a private IP address for inbound traffic...
     */
    destination_address_prefix = azurerm_linux_virtual_machine.ldaps.private_ip_address
  }

  security_rule {
    access                 = "Allow"
    direction              = "Inbound"
    name                   = "allow-ldaps"
    priority               = 110
    protocol               = "Tcp"
    source_port_range      = "*"
    source_address_prefix  = "*"
    destination_port_range = "636"
    /*
     * From Microsoft's online docs: "If you specify an address for an Azure
     * resource, specify the private IP address assigned to the resource.
     * Network security groups are processed after Azure translates a public IP
     * address to a private IP address for inbound traffic...
     */
    destination_address_prefix = azurerm_linux_virtual_machine.ldaps.private_ip_address
  }
}

resource "azurerm_network_interface_security_group_association" "ldaps_sga" {
  network_interface_id      = azurerm_network_interface.ldaps_nic.id
  network_security_group_id = azurerm_network_security_group.sg_ldaps.id
}

resource "azurerm_virtual_machine_extension" "ldaps_setup" {
  name                 = "${var.ldaps_name}-ldaps-setup"
  virtual_machine_id   = azurerm_linux_virtual_machine.ldaps.id
  publisher            = "Microsoft.Azure.Extensions"
  type                 = "CustomScript"
  type_handler_version = "2.0"

  protected_settings = <<PROT
       {
               "script": "${base64encode(file(var.ldaps_launch_script))}"
       }
       PROT

  tags = {
    environment = "Production"
  }
}
