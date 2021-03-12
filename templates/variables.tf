variable "tags" {
  default          = {
    ch_cloud       = "{{Target}}"
    ch_environment = "demo"
    ch_org         = "sales"
    ch_team        = "fieldeng"
    ch_project     = "demo"
    ch_user        = "{{UserName}}"
  }
}

variable "region" {
  default = "{{Region}}"
}

variable "resource_group_name" {
  default = "rg-{{ShortName}}"
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

variable "mariadb_server_name" {
  default = "mariadb-server-{{ShortName}}"
}

variable "db_name" {
  default = "{{DBName}}"
}

variable "db_name_el" {
  default = "{{DBNameEventLogger}}"
}

variable "db_user" {
  default = "{{DBUser}}"
}

variable "db_password" {
  default = "{{DBPassword}}"
}

variable "storage_account" {
  default = "{{StorageAccount}}"
}

variable "bucket_name" {
  default = "{{BucketName}}"
}
