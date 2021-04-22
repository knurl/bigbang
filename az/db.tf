/*
 * For both postgres and mysql, we need private DNS zones that are linked to
 * our VNET. The linking makes it so hosts on that VNET use the private DNS
 * first, which in turn forwards to the main Azure DNS.
 */
resource "azurerm_private_dns_zone" "prvdns-postgres" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone" "prvdns-mysql" {
  name                = "privatelink.mysql.database.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "dnslink-postgres" {
  name                  = "${azurerm_virtual_network.vnet.name}-dnslink-postgres"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.prvdns-postgres.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  tags                  = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "dnslink-mysql" {
  name                  = "${azurerm_virtual_network.vnet.name}-dnslink-mysql"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.prvdns-mysql.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  tags                  = var.tags
}

/*
 * Create all the database servers.
 */

resource "azurerm_postgresql_server" "evtlog" {
  name                = var.evtlog_server_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  administrator_login          = var.db_user
  administrator_login_password = var.db_password

  sku_name   = "GP_Gen5_2"
  version    = "11"
  storage_mb = 20480

  geo_redundant_backup_enabled = false
  auto_grow_enabled            = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags = var.tags
}

resource "azurerm_postgresql_server" "postgres" {
  name                = var.postgres_server_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  administrator_login          = var.db_user
  administrator_login_password = var.db_password

  sku_name   = "GP_Gen5_2"
  version    = "11"
  storage_mb = 20480

  geo_redundant_backup_enabled = false
  auto_grow_enabled            = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags = var.tags
}

resource "azurerm_mysql_server" "mysql" {
  name                = var.mysql_server_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  administrator_login          = var.db_user
  administrator_login_password = var.db_password

  sku_name   = "GP_Gen5_2"
  version    = "5.6"
  storage_mb = 20480

  geo_redundant_backup_enabled = false
  auto_grow_enabled            = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags = var.tags
}

/*
 * Now create all the databases in the servers.
 */

resource "azurerm_postgresql_database" "evtlog_db" {
  name                = var.db_name_evtlog
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_postgresql_server.evtlog.name
  charset             = var.charset
  collation           = "English_United States.1252"
}

resource "azurerm_postgresql_database" "postgres_db" {
  name                = var.db_name
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_postgresql_server.postgres.name
  charset             = var.charset
  collation           = "English_United States.1252"
}

resource "azurerm_mysql_database" "mysql_db" {
  name                = var.db_name
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_mysql_server.mysql.name
  charset             = var.charset
  collation           = var.mysql_collation
}

/*
 * We need private endpoints for each of the databases, so we can connect to
 * them from a private IP in our VNET
 */

resource "azurerm_private_endpoint" "pe_evtlog" {
  name                = "${var.evtlog_server_name}-pe"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.evtlog_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_postgresql_server.evtlog.id
    subresource_names              = ["postgresqlServer"]
  }

  private_dns_zone_group {
    name                 = "${var.evtlog_server_name}-dnszg"
    private_dns_zone_ids = [azurerm_private_dns_zone.prvdns-postgres.id]
  }

  tags = var.tags
}

resource "azurerm_private_endpoint" "pe_postgres" {
  name                = "${var.postgres_server_name}-pe"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.postgres_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_postgresql_server.postgres.id
    subresource_names              = ["postgresqlServer"]
  }

  private_dns_zone_group {
    name                 = "${var.postgres_server_name}-dnszg"
    private_dns_zone_ids = [azurerm_private_dns_zone.prvdns-postgres.id]
  }

  tags = var.tags
}

resource "azurerm_private_endpoint" "pe_mysql" {
  name                = "${var.mysql_server_name}-pe"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.mysql_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_mysql_server.mysql.id
    subresource_names              = ["mysqlServer"]
  }

  private_dns_zone_group {
    name                 = "${var.mysql_server_name}-dnszg"
    private_dns_zone_ids = [azurerm_private_dns_zone.prvdns-mysql.id]
  }

  tags = var.tags
}
