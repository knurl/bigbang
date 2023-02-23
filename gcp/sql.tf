/*
 * One of GCP's quirks is that it doesn't immediately delete database
 * instances. They hang around for a week, so if you try to create a new
 * database with the same name, you'll get an error. For that reason it's
 * strongly recommended you include a random string as part of the name.
 */
resource "random_id" "db_name_suffix" {
  byte_length = 4
}

/*
 * Create all of the database instances ("servers")
 */

resource "google_sql_database_instance" "sql_postgres" {
  name    = "${var.postgres_server_name}-${random_id.db_name_suffix.hex}"
  region  = var.region
  project = data.google_project.project.project_id

  database_version = join("_", ["POSTGRES", var.postgresql_version])
  # depends_on is required here per the docs
  depends_on          = [google_service_networking_connection.pvpc_peering]
  deletion_protection = false

  settings {
    tier              = var.db_instance_type
    availability_type = "ZONAL"

    location_preference {
      zone = var.zone
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    user_labels = var.tags
  }
}

resource "google_sql_database_instance" "sql_mysql" {
  count   = var.mysql_enabled ? 1 : 0
  name    = "${var.mysql_server_name}-${random_id.db_name_suffix.hex}"
  region  = var.region
  project = data.google_project.project.project_id

  database_version = join("_", concat(["MYSQL"], split(".", var.mysql_version)))
  # depends_on is required here per the docs
  depends_on          = [google_service_networking_connection.pvpc_peering]
  deletion_protection = false

  settings {
    tier              = var.db_instance_type
    availability_type = "ZONAL"

    location_preference {
      zone = var.zone
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    user_labels = var.tags
  }
}

/*
 * Create the users who will access the databases.
 */
resource "google_sql_user" "user_postgres" {
  project  = data.google_project.project.project_id
  instance = google_sql_database_instance.sql_postgres.name
  name     = var.db_user
  password = var.db_password
}

resource "google_sql_user" "user_mysql" {
  count    = var.mysql_enabled ? 1 : 0
  project  = data.google_project.project.project_id
  instance = var.mysql_enabled ? google_sql_database_instance.sql_mysql.0.name : null
  name     = var.db_user
  password = var.db_password
}

/*
 * Create all of the databases in the servers.
 */

resource "google_sql_database" "db_postgres_evtlog" {
  name            = var.db_name_evtlog
  project         = data.google_project.project.project_id
  instance        = google_sql_database_instance.sql_postgres.name
  charset         = var.postgres_charset
  collation       = var.postgres_collation
  deletion_policy = "ABANDON"
}

resource "google_sql_database" "db_postgres_hms" {
  name            = var.db_name_hms
  project         = data.google_project.project.project_id
  instance        = google_sql_database_instance.sql_postgres.name
  charset         = var.postgres_charset
  collation       = var.postgres_collation
  deletion_policy = "ABANDON"
}

resource "google_sql_database" "db_postgres_cachesrv" {
  count     = var.cache_service_enabled ? 1 : 0
  name      = var.db_name_cachesrv
  project   = data.google_project.project.project_id
  instance  = google_sql_database_instance.sql_postgres.name
  charset   = var.postgres_charset
  collation = var.postgres_collation
}

resource "google_sql_database" "db_postgres" {
  count           = var.postgres_enabled ? 1 : 0
  name            = var.db_name
  project         = data.google_project.project.project_id
  instance        = google_sql_database_instance.sql_postgres.name
  charset         = var.postgres_charset
  collation       = var.postgres_collation
  deletion_policy = "ABANDON"
  #  depends_on      = [google_sql_user.user_postgres]
}

resource "google_sql_database" "db_mysql" {
  count     = var.mysql_enabled ? 1 : 0
  name      = var.db_name
  project   = data.google_project.project.project_id
  instance  = var.mysql_enabled ? google_sql_database_instance.sql_mysql.0.name : null
  charset   = var.mysql_charset
  collation = var.mysql_collation
  #  depends_on = [google_sql_user.user_mysql]
}
