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

variable "domain" {
  default = "{{Domain}}"
}

variable "cluster_name" {
  default = "{{ClusterName}}"
}

variable "network_name" {
  default = "{{NetwkName}}"
}

variable "policy_name" {
  default = "{{ShortName}}-policy"
}

variable "instance_types" {
  type = list(string)
  default = {{ InstanceTypes|tojson }}
}

variable "small_instance_type" {
  default = "{{SmallInstanceType}}"
}

variable "bastion_name" {
  default = "{{ShortName}}-bastion"
}

variable "bastion_fw_ingress" {
  default = ["{{MyPublicIP}}/32"]
}

variable "node_count" {
  default = "{{NodeCount}}"
}

variable "max_pods_per_node" {
  default = "{{MaxPodsPerNode}}"
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
variable "sg_name" {
  default = "{{ShortName}}-sg"
}
{% elif Target == "az" %}
variable "my_cidr" {
  default = "{{MyCIDR}}"
}

variable "resource_group_name" {
  default = "{{ResourceGroup}}"
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
