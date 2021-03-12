module "subnet_addrs" {
  source          = "hashicorp/subnets/cidr"
  version         = "1.0.0"
  base_cidr_block = var.my_cidr
  networks = [
    {
      name     = "prv_a",
      new_bits = 2 # 00.1 - 63.254 = 16382
    },
    {
      name     = "prv_b",
      new_bits = 2 # 64.1 - 127.254 = 16382
    },
    {
      name     = "prv_c",
      new_bits = 2 # 128.1 - 191.254 = 16382
    },
    {
      name     = "db_a",
      new_bits = 4 # 192.1 - 207.254 = 4094
    },
    {
      name     = "db_b",
      new_bits = 4 # 208.1 - 223.254 = 4094
    },
    {
      name     = "db_c",
      new_bits = 4 # 224.1 - 239.254 = 4094
    },
    {
      name     = "pub_a",
      new_bits = 6 # 240.1 - 243.254 = 1022
    },
    {
      name     = "pub_b",
      new_bits = 6 # 244.1 - 247.254 = 1022
    },
    {
      name     = "pub_c",
      new_bits = 6 # 248.1 - 251.254 = 1022
    } # 1022 hosts remaining to be assigned
  ]
}
