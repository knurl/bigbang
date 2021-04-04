variable "tags" {
  default          = {
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

variable "resource_group_name" {
  default = "{{ResourceGroup}}"
}

variable "my_cidr" {
  default = "{{MyCIDR}}"
}

variable "cluster_name" {
  default = "{{ClusterName}}"
}

variable "instance_type" {
  default = "{{InstanceType}}"
}

variable "bastion_instance_type" {
  default = "{{BastionInstanceType}}"
}

variable "forwarder_script" {
  default = "{{ForwarderScript}}"
}

variable "node_count" {
  default = "{{NodeCount}}"
}

variable "vpn_instance_id" {
  default = "{{VpnInstanceId}}"
}

variable "vpn_vnet_resource_group" {
  default = "{{VpnVnetResourceGroup}}"
}

variable "vpn_vnet_name" {
  default = "{{VpnVnetName}}"
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

variable "storage_account" {
  default = "{{StorageAccount}}"
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
