variable "tags" {
  default = {
    cloud       = "{{Target}}"
    environment = "demo"
    org         = "sales"
    team        = "sa"
    project     = "experiment"
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

variable "my_cidr" {
  default = "{{MyCIDR}}"
}

variable "cluster_name" {
  default = "{{ClusterName}}"
}

variable "network_name" {
  default = "{{ClusterName}}-net"
}

variable "instance_type" {
  default = "{{InstanceType}}"
}

variable "small_instance_type" {
  default = "{{SmallInstanceType}}"
}

variable "db_instance_type" {
  default = "{{DbInstanceType}}"
}

variable "bastion_name" {
  default = "bastion-{{ShortName}}"
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
  default = "ldaps-{{ShortName}}"
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
  default = "evtlog-server-{{ShortName}}"
}

variable "postgres_server_name" {
  default = "postgres-server-{{ShortName}}"
}

variable "postgresql_version" {
  default = "11"
}

variable "mysql_server_name" {
  default = "mysql-server-{{ShortName}}"
}

variable "mysql_version" {
  default = "8.0"
}

variable "db_name" {
  default = "{{DBName}}"
}

variable "db_name_evtlog" {
  default = "{{DBNameEventLogger}}"
}

variable "db_user" {
  default = "{{DBUser}}"
}

variable "db_password" {
  default = "{{DBPassword}}"
}

variable "redshift_cluster_name" {
  default = "redshift-cluster-{{ShortName}}"
}

variable "postgres_charset" {
  default = "UTF8"
}

variable "postgres_collation" {
  default = "en_US.UTF8"
}

variable "azure_postgres_collation" {
  default = "en-US"
}

variable "mysql_charset" {
  default = "utf8mb4"
}

variable "mysql_collation" {
  default = "utf8mb4_0900_ai_ci"
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

{% if Target == "az" %}

# Azure-specific stuff
#
variable "storage_account" {
  default = "{{StorageAccount}}"
}

variable "resource_group_name" {
  default = "{{ResourceGroup}}"
}

variable "synapse_ws_name" {
  default = "synapse-ws-{{ShortName}}"
}

{% elif Target == "gcp" %}

#
# Google-specific stuff
#
variable "gcp_project_id" {
  default = "{{GcpProjectId}}"
}

{% endif %}
