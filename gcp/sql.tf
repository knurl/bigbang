/*
 * One of GCP's quirks is that it doesn't immediately delete databases. They
 * hang around for a week, so if you try to create a new database with the same
 * name, you'll get an error. For that reason it's strongly recommended you
 * include a random string as part of the database name.
 */
resource "random_id" "db_name_suffix" {
  byte_length = 4
}

/*
 * Create all of the database instances ("servers")
 */

resource "google_sql_database_instance" "sql_evtlog" {
  name                = "${var.evtlog_server_name}-${random_id.db_name_suffix.hex}"
  region              = var.region
  project             = data.google_project.project.project_id

  database_version    = "POSTGRES_11"
  depends_on          = [google_service_networking_connection.pvpc_peering]
  deletion_protection = false

  settings {
    tier              = "db-g1-small"
    availability_type = "ZONAL"

    location_preference {
      zone            = var.zone
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = data.google_compute_network.vpc.id
    }

    user_labels       = var.tags
  }
}

resource "google_sql_database_instance" "sql_postgres" {
  name                = "${var.postgres_server_name}-${random_id.db_name_suffix.hex}"
  region              = var.region
  project             = data.google_project.project.project_id

  database_version    = "POSTGRES_11"
  depends_on          = [google_service_networking_connection.pvpc_peering]
  deletion_protection = false

  settings {
    tier              = "db-g1-small"
    availability_type = "ZONAL"

    location_preference {
      zone            = var.zone
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = data.google_compute_network.vpc.id
    }

    user_labels       = var.tags
  }
}

resource "google_sql_database_instance" "sql_mysql" {
  name                = "${var.mysql_server_name}-${random_id.db_name_suffix.hex}"
  region              = var.region
  project             = data.google_project.project.project_id

  database_version    = "MYSQL_5_6"
  depends_on          = [google_service_networking_connection.pvpc_peering]
  deletion_protection = false

  settings {
    tier              = "db-g1-small"
    availability_type = "ZONAL"

    location_preference {
      zone            = var.zone
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = data.google_compute_network.vpc.id
    }

    user_labels       = var.tags
  }
}

/*
 * Create the users who will access the databases.
 */

resource "google_sql_user" "user_evtlog" {
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_evtlog.name
  name       = var.db_user
  password   = var.db_password
  depends_on = [google_sql_database_instance.sql_evtlog]
}

resource "google_sql_user" "user_postgres" {
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_postgres.name
  name       = var.db_user
  password   = var.db_password
  depends_on = [google_sql_database_instance.sql_postgres]
}

resource "google_sql_user" "user_mysql" {
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_mysql.name
  name       = var.db_user
  password   = var.db_password
  depends_on = [google_sql_database_instance.sql_mysql]
}

/*
 * Create all of the databases in the servers.
 */

resource "google_sql_database" "db_evtlog" {
  name       = var.db_name_evtlog
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_evtlog.name
  charset    = var.charset
  collation  = "en_US.UTF8"
  depends_on = [google_sql_user.user_evtlog]
}

resource "google_sql_database" "db_postgres" {
  name       = var.db_name
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_postgres.name
  charset    = var.charset
  collation  = "en_US.UTF8"
  depends_on = [google_sql_user.user_postgres]
}

resource "google_sql_database" "db_mysql" {
  name       = var.db_name
  project    = data.google_project.project.project_id
  instance   = google_sql_database_instance.sql_mysql.name
  charset    = var.charset
  collation  = var.mysql_collation
  depends_on = [google_sql_user.user_mysql]
}
