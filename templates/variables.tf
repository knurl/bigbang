# FIXME Change sizing back to previous project name
variable "tags" {
  default = {
    cloud       = "{{Target}}"
    environment = "demo"
    org         = "sales"
    team        = "sa"
    project     = "sizing"
    user        = "{{UserName}}"
    info        = "{{Zone}}"
  }
}

variable "region" {
  default = "{{Region}}"
}

variable "zone" {
  default = "{{Zone}}"
}

variable "cluster_name" {
  default = "{{ClusterName}}"
}

variable "network_name" {
  default = "{{NetwkName}}"
}

variable "policy_name" {
  default = "{{LongName}}-policy"
}

variable "capacity_type" {
  default = "{{CapacityType}}"
}

variable "instance_types" {
  type = list(string)
  default = {{ InstanceTypes|tojson }}
}

variable "small_instance_type" {
  default = "{{SmallInstanceType}}"
}

variable "db_instance_type" {
  default = "{{DbInstanceType}}"
}

variable "bastion_name" {
  default = "{{LongName}}-bastion"
}

variable "bastion_fw_ingress" {
  {% if DisableBastionFw %}
  default = ["0.0.0.0/0"]
  {% else %}
  {% if DownstreamSG %}
  default = ["{{MyPublicIP}}/32", "{{UpstrBastion}}"]
  {% else %}
  default = ["{{MyPublicIP}}/32"]
  {% endif %}
  {% endif %}
}

variable "upstream_stargate" {
  default = "{{UpstreamSG}}" == "True" ? true : false
}

variable "ldaps_name" {
  default = "{{LongName}}-ldaps"
}

variable "ldaps_launch_script" {
  default = "{{LdapLaunchScript}}"
}

variable "bastion_launch_script" {
  default = "{{BastionLaunchScript}}"
}

variable "node_count" {
  default = "{{NodeCount}}"
}

variable "max_pods_per_node" {
  default = "{{MaxPodsPerNode}}"
}

variable "evtlog_server_name" {
  default = "{{LongName}}-evtlog"
}

variable "cache_service_enabled" {
  default = "{{CacheServiceEnabled}}" == "True" ? "true" : "false"
}

variable "cachesrv_server_name" {
  default = "{{LongName}}-cachesrv"
}

variable "hmsdb_server_name" {
  default = "{{LongName}}-hmsdb"
}

variable "postgres_server_name" {
  default = "{{LongName}}-postgres"
}

variable "postgresql_version" {
  default = "11"
}

variable "postgres_charset" {
  default = "UTF8"
}

variable "postgres_collation" {
  default = "en_US.UTF8"
}

variable "postgres_enabled" {
  default = "{{PostgreSqlEnabled}}" == "True" ? true : false
}

variable "mysql_server_name" {
  default = "{{LongName}}-mysql"
}

variable "mysql_version" {
  default = "8.0"
}

variable "mysql_charset" {
  default = "utf8mb4"
}

variable "mysql_collation" {
  default = "utf8mb4_0900_ai_ci"
}

variable "mysql_enabled" {
  default = "{{MySqlEnabled}}" == "True" ? true : false
}

variable "db_name" {
  default = "{{DBName}}"
}

variable "db_name_evtlog" {
  default = "{{DBNameEventLogger}}"
}

variable "db_name_hms" {
  default = "{{DBNameHms}}"
}

variable "db_name_cachesrv" {
  default = "{{DBNameCacheSrv}}"
}

variable "db_user" {
  default = "{{DBUser}}"
}

variable "db_password" {
  default = "{{DBPassword}}"
}

variable "bucket_name" {
  default = "{{BucketName}}"
}

variable "my_public_ip" {
  default = "{{MyPublicIP}}"
}

variable "ssh_public_key" {
  default = <<-RSAKEY
  {{SshPublicKey}}
  RSAKEY
}

{% if Target == "aws" %}
variable "redshift_cluster_name" {
  default = "{{LongName}}-redshift"
}

variable "sg_name" {
  default = "{{LongName}}-sg"
}
{% elif Target == "az" %}
variable "my_cidr" {
  default = "{{MyCIDR}}"
}

variable "azure_postgres_collation" {
  default = "en-US"
}

variable "storage_account" {
  default = "{{StorageAccount}}"
}

variable "resource_group_name" {
  default = "{{ResourceGroup}}"
}

variable "synapse_ws_name" {
  default = "{{LongName}}-synapse-ws"
}
{% elif Target == "gcp" %}
variable "my_cidr" {
  default = "{{MyCIDR}}"
}

variable "gcp_project_id" {
  default = "{{GcpProjectId}}"
}

# account of the user logged in
variable "gcp_account" {
  default = "{{GcpAccount}}"
}
{% endif %}
