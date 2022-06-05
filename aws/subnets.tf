module "subnet_addrs" {
  source          = "hashicorp/subnets/cidr"
  version         = "1.0.0"
  base_cidr_block = var.my_cidr
  networks = [
    {
      name     = "prv_a",
      new_bits = 2 # 00.1 - 63.254 = 16382 x.x.0.0/18
    },
    {
      name     = "prv_b",
      new_bits = 2 # 64.1 - 127.254 = 16382 x.x.64.0/18
    },
    {
      name     = "db_a",
      new_bits = 4 # 192.1 - 207.254 = 4094 x.x.192.0/20
    },
    {
      name     = "db_b",
      new_bits = 4 # 208.1 - 223.254 = 4094 x.x.208.0/20
    },
    {
      name     = "pub_a",
      new_bits = 6 # 240.1 - 243.254 = 1022 x.x.240.0/22
    },
    {
      name     = "pub_b",
      new_bits = 6 # 244.1 - 247.254 = 1022 x.x.244.0/22
    },
    {
      name     = "red_a",
      new_bits = 8 # 252.1 - 252.254 = 254 x.x.252/24
    },
    {
      name     = "red_b",
      new_bits = 8 # 253.1 - 253.254 = 254 x.x.253/24
    }              # 254 hosts remaining to be assigned
  ]
}
