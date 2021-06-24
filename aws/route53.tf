resource "aws_route53_zone" "private_dns" {
  name          = "az.starburstdata.net"
  tags          = var.tags
  force_destroy = true

  vpc {
    vpc_id = module.vpc.vpc_id
  }
}

resource "aws_route53_record" "ldap_a_record" {
  zone_id = aws_route53_zone.private_dns.zone_id
  name    = "ldap"
  type    = "A"
  ttl     = "3600"
  records = [aws_instance.ldaps.private_ip]
}

resource "aws_route53_record" "bastion_a_record" {
  zone_id = aws_route53_zone.private_dns.zone_id
  name    = "bastion"
  type    = "A"
  ttl     = "3600"
  records = [aws_instance.bastion.private_ip]
}
