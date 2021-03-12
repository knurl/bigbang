/*
 * Ordinary PostgreSQL Server for demos, as a typical data source
 */
resource "azurerm_postgresql_server" "postgres" {
  name                          = var.postgres_server_name
  location                      = azurerm_resource_group.rg.location
  resource_group_name           = azurerm_resource_group.rg.name

  administrator_login           = var.db_user
  administrator_login_password  = var.db_password

  sku_name                      = "GP_Gen5_2"
  version                       = "11"
  storage_mb                    = 20480

  geo_redundant_backup_enabled  = false
  auto_grow_enabled             = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags                          = var.tags
}

resource "azurerm_postgresql_database" "postgres_db" {
  name                = var.db_name
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_postgresql_server.postgres.name
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_private_dns_zone" "prvdns-postgres" {
  name                = "privatelink.postgres.database.azure.com"
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

resource "azurerm_private_endpoint" "pe_postgres" {
  name                             = "${var.postgres_server_name}-pe"
  location                         = azurerm_resource_group.rg.location
  resource_group_name              = azurerm_resource_group.rg.name
  subnet_id                        = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.postgres_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_postgresql_server.postgres.id
    subresource_names              = ["postgresqlServer"]
  }

  private_dns_zone_group {
    name                           = "${var.postgres_server_name}-dnszg"
    private_dns_zone_ids           = [azurerm_private_dns_zone.prvdns-postgres.id]
  }

  tags                             = var.tags
}

/*
 * PostgreSQL Server for Event Logger
 */
resource "azurerm_postgresql_server" "evtlog" {
  name                          = var.evtlog_server_name
  location                      = azurerm_resource_group.rg.location
  resource_group_name           = azurerm_resource_group.rg.name

  administrator_login           = var.db_user
  administrator_login_password  = var.db_password

  sku_name                      = "GP_Gen5_2"
  version                       = "11"
  storage_mb                    = 20480

  geo_redundant_backup_enabled  = false
  auto_grow_enabled             = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags                          = var.tags
}

resource "azurerm_postgresql_database" "evtlog_db" {
  name                = var.db_name_el
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_postgresql_server.evtlog.name
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_private_endpoint" "pe_el" {
  name                             = "${var.evtlog_server_name}-pe"
  location                         = azurerm_resource_group.rg.location
  resource_group_name              = azurerm_resource_group.rg.name
  subnet_id                        = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.evtlog_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_postgresql_server.evtlog.id
    subresource_names              = ["postgresqlServer"]
  }

  private_dns_zone_group {
    name                           = "${var.evtlog_server_name}-dnszg"
    private_dns_zone_ids           = [azurerm_private_dns_zone.prvdns-postgres.id]
  }

  tags                             = var.tags
}

/*
 * Don't need a new private dns zone here for the Postgres event-logger
 * database, as we've already created one for all Postgres databases above, and
 * we'll just use that one.
 */

/*
 * Ordinary MariaDB Server for demos, as a typical data source
 */
resource "azurerm_mariadb_server" "mariadb" {
  name                          = var.mariadb_server_name
  location                      = azurerm_resource_group.rg.location
  resource_group_name           = azurerm_resource_group.rg.name

  administrator_login           = var.db_user
  administrator_login_password  = var.db_password

  sku_name                      = "GP_Gen5_2"
  version                       = "10.3"
  storage_mb                    = 20480

  geo_redundant_backup_enabled  = false
  auto_grow_enabled             = false

  public_network_access_enabled = false
  ssl_enforcement_enabled       = false

  tags                          = var.tags
}

resource "azurerm_mariadb_database" "mariadb_db" {
  name                = var.db_name
  resource_group_name = azurerm_resource_group.rg.name
  server_name         = azurerm_mariadb_server.mariadb.name
  charset             = "utf8"
  collation           = "utf8_general_ci"
}

resource "azurerm_private_dns_zone" "prvdns-mariadb" {
  name                = "privatelink.mariadb.database.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "dnslink-mariadb" {
  name                  = "${azurerm_virtual_network.vnet.name}-dnslink-mariadb"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.prvdns-mariadb.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  tags                  = var.tags
}

resource "azurerm_private_endpoint" "pe_mariadb" {
  name                             = "${var.mariadb_server_name}-pe"
  location                         = azurerm_resource_group.rg.location
  resource_group_name              = azurerm_resource_group.rg.name
  subnet_id                        = azurerm_subnet.db_sub.id

  private_service_connection {
    name                           = "${var.mariadb_server_name}-psc"
    is_manual_connection           = false
    private_connection_resource_id = azurerm_mariadb_server.mariadb.id
    subresource_names              = ["mariadbServer"]
  }

  private_dns_zone_group {
    name                           = "${var.mariadb_server_name}-dnszg"
    private_dns_zone_ids           = [azurerm_private_dns_zone.prvdns-mariadb.id]
  }

  tags                             = var.tags
}

