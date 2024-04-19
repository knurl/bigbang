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
      name     = "prv_c",
      new_bits = 2 # 128.1 - 191.254 = 16382
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
      name     = "pub_c",
      new_bits = 6 # 248.1 - 251.254 = 1022
    }              # 1022 hosts remaining to be assigned
  ]
}
