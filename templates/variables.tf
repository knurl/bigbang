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

variable "bastion_name" {
  default = "bastion-{{ShortName}}"
}

variable "ldaps_name" {
  default = "ldaps-{{ShortName}}"
}

variable "ldaps_launch_script" {
  default = "{{LdapLaunchScript}}"
}

variable "small_instance_type" {
  default = "{{SmallInstanceType}}"
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

variable "mysql_server_name" {
  default = "mysql-server-{{ShortName}}"
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

variable "charset" {
  default = "utf8"
}

variable "mysql_collation" {
  default = "utf8_general_ci"
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

variable "mc_stargate_enabled" {
  default = "{{MCStargate}}" == "True" ? true : false
}

{% if Target == "az" %}
#
# Azure-specific stuff
#
variable "storage_account" {
  default = "{{StorageAccount}}"
}

variable "resource_group_name" {
  default = "{{ResourceGroup}}"
}
{% elif Target == "gcp" %}
#
# Google-specific stuff
#
variable "gcp_project_id" {
  default = "{{GcpProjectId}}"
}
{% endif %}
