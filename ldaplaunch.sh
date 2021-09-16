#!/bin/bash
  
# Install Slapd !

# update first
apt-get -q -y update

# remove any existing install first
sudo apt-get --purge remove -y slapd ldap-utils

# get rid of the database
sudo rm -rf /var/lib/ldap
sudo rm -rf /etc/ldap

cat << EOM | sudo debconf-set-selections
slapd slapd/password1 password admin
slapd slapd/internal/adminpw password admin
slapd slapd/internal/generated_adminpw password admin
slapd slapd/password2 password admin
slapd slapd/domain string az.starburstdata.net
slapd shared/organization string fieldeng
slapd slapd/purge_database boolean true
slapd slapd/move_old_database boolean false
slapd slapd/backend string MDB
slapd slapd/no_configuration boolean false
EOM

export DEBIAN_FRONTEND=noninteractive

# now reinstall slapd
sudo apt-get install -y slapd ldap-utils

# set password
sudo slappasswd -s admin
cat <<EOM | sudo tee -a /etc/ldap/slapd-key.pem
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDILqZDWl0au8so
2ld8p7oxm0W1swkdRZDr/qIfDJ4lMlHQx/0C26HoQpcTRZ6+XAh2hk5Fo6kifWfh
1F8Whnk+c2UON1Uu82/ZpfOpPZPuiowEF6aC1LN+0WLpDXgnjAL7+cSmSHtTIOv4
asrCPOVeunM6/TknaKRV8gyoHEdncMdhylt4KEOJtJCZlKIxPLf7dH11+bPCUNEf
7Rq+kRaIEIgmUEq0+luD8CQ4bYipv0QEX1Ii7DrbkqsKbRHS1WvwAbXKEO9+bAlb
XcN1bpJgdUWbSXP7Mn6mctL18pe0wpNLTmxMjw2ILoQu+Zr4d/FF2BnugevLP5JL
yd/oMCZrAgMBAAECggEBAKUKUOmWxswTqBu2aArN/iSH76EuSoVnpWPsO519uaTR
J8MKHv8MNSBYRlYNQCORnSia8k1X8UoOOmdlwD/B/pQOb3KZDBH5gm3e9FTEAALb
FzUIiq+yzYnw96tM/5MbTBqSgh7WA1c1/VaCNUiPDExdTEOGImjrTRHOzcCMEBKm
4kiPZmbthHBAmHSQup6z4KI0BfxHnlzg/kasW1iT/Whieg0QxldegrVmmkKKuoW+
4DV626X9Ik9WDTumDw46K5AJw7HUwSodxMjMAY6ZeDmfcOklLXcUniASbCptZ+My
mcsWYZs+3WCDoWWHH/lDmVdGcyRBC/ocYt8IlTNRVgECgYEA9QMCNhksbiKUErmJ
ksu+LrBU222QtBzYPqKLM+uZxfeuMewd6md6IuKzgzu5ANOlAUNT754BybBEXs7a
zHaKJIQR8JHowRwENYuZkdHxFsEg+b/RZ3i4pEgsbAXpOPzae7qb91fOhCvAVCE6
K5qHXDjpjmgv4GdJOoUZV9kHwpsCgYEA0Sjzb8iQb+huAD0XMW+8Pwy2X8ayZ7U9
662e/hLMdJbncTd+A+5qfiBSKN2ZyOBeJ9JteUHcYOMsgQ/kF3oeR3L2HtgRzc/M
zrOP/Vt/RRpAdfccEFFX3eiyJD4SiBsp+4cRnDdiV/AY+L8/S5WQrJMv11tRb9uL
xcsvCH7dwHECgYEAkpGjMAOtLZFn7S+q2fMiKUH48W9A4k5jGk0YYw3s5p29SkYK
u1/9k4L0imwexxzVF8VUIALw5NuaevDZuPisuR18seJHT8ZXykRhsPbbd5Y/CMi0
F2cDZdt7H4AFvb6dYOkIRlXzx+N4YZui9dSyZvvw0+0FvwNqriRTPdcqKkMCgYAZ
vhKIFYVBYLf5K4upN/lRQT1I+GmIvhPK5+mDl8i2KMR/eLb3wOY2c7/o6607vfGY
sRtsKyD2g788ezo1cYA8hvenwCwgyoyIfC0in5pAZQS+ABXiJEDOPQ9/ymv5eG5o
WK1gLqjZ7eEE7HTb1qKhutPOi5ywSbMgOuuk/ghI4QKBgE7QS+QjeCMpn7Ckai1b
S89SWeUl6USfBbA0NAodx+JmaRYpdfvz65IpiM4h2pu1X7OetUkoTFq8NnodEhi2
YFGQlmjHE1+SZCXQ05+08Cm5ib2YDBscPIeNvdFylGCD7En3LiP3ntvymFeqzzkg
augQ/11D6BsLJWLVH2O+9GU3
-----END PRIVATE KEY-----
EOM
cat <<EOM | sudo tee -a /etc/ldap/slapd-cert.pem
-----BEGIN CERTIFICATE-----
MIIFNzCCBB+gAwIBAgISBO+amK4UmgnxgHnjWj3rAyA5MA0GCSqGSIb3DQEBCwUA
MDIxCzAJBgNVBAYTAlVTMRYwFAYDVQQKEw1MZXQncyBFbmNyeXB0MQswCQYDVQQD
EwJSMzAeFw0yMTA5MTYxMTU2NTVaFw0yMTEyMTUxMTU2NTRaMCQxIjAgBgNVBAMT
GWxkYXAuYXouc3RhcmJ1cnN0ZGF0YS5uZXQwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDILqZDWl0au8so2ld8p7oxm0W1swkdRZDr/qIfDJ4lMlHQx/0C
26HoQpcTRZ6+XAh2hk5Fo6kifWfh1F8Whnk+c2UON1Uu82/ZpfOpPZPuiowEF6aC
1LN+0WLpDXgnjAL7+cSmSHtTIOv4asrCPOVeunM6/TknaKRV8gyoHEdncMdhylt4
KEOJtJCZlKIxPLf7dH11+bPCUNEf7Rq+kRaIEIgmUEq0+luD8CQ4bYipv0QEX1Ii
7DrbkqsKbRHS1WvwAbXKEO9+bAlbXcN1bpJgdUWbSXP7Mn6mctL18pe0wpNLTmxM
jw2ILoQu+Zr4d/FF2BnugevLP5JLyd/oMCZrAgMBAAGjggJTMIICTzAOBgNVHQ8B
Af8EBAMCBaAwHQYDVR0lBBYwFAYIKwYBBQUHAwEGCCsGAQUFBwMCMAwGA1UdEwEB
/wQCMAAwHQYDVR0OBBYEFAXtOCU+M/ZPIOBpYa/hVNHGHAajMB8GA1UdIwQYMBaA
FBQusxe3WFbLrlAJQOYfr52LFMLGMFUGCCsGAQUFBwEBBEkwRzAhBggrBgEFBQcw
AYYVaHR0cDovL3IzLm8ubGVuY3Iub3JnMCIGCCsGAQUFBzAChhZodHRwOi8vcjMu
aS5sZW5jci5vcmcvMCQGA1UdEQQdMBuCGWxkYXAuYXouc3RhcmJ1cnN0ZGF0YS5u
ZXQwTAYDVR0gBEUwQzAIBgZngQwBAgEwNwYLKwYBBAGC3xMBAQEwKDAmBggrBgEF
BQcCARYaaHR0cDovL2Nwcy5sZXRzZW5jcnlwdC5vcmcwggEDBgorBgEEAdZ5AgQC
BIH0BIHxAO8AdQBc3EOS/uarRUSxXprUVuYQN/vV+kfcoXOUsl7m9scOygAAAXvu
rnSkAAAEAwBGMEQCIBZxexs3+oWvaYGQ8PizsULvFfp6fOOwb7b8Z08D/6yIAiAo
OKTd0zyBey+GewA0UfxeawYGTjh8Ady5yEWENvbg4gB2APZclC/RdzAiFFQYCDCU
Vo7jTRMZM7/fDC8gC8xO8WTjAAABe+6udIoAAAQDAEcwRQIgXtkoSYt0heX5Lg/p
SRPkzoMhnlFb7+fHY69IXqAclXsCIQCrCwUaQruAxYVLzcXv1epNt+ikbOAgnEqO
1ATFUklSATANBgkqhkiG9w0BAQsFAAOCAQEAF29PEBR7McZ7MNA4cfVmuUklqXF6
+0I4RKp6SVHzofvzOyEYc0cFaBH2VaXj/qQ7s/OkOLbFVv6ZS8lPKxKdVRzViDvb
H5Fq6CswFAGKvqxuVsRIp49Ubb+y6ZgdbyQ/d8kauhFsnbaZzV2SaX8MR7otXyEZ
OvxZy2Q6nbrCFiyzPhXkG1mdFbZTg+PokWm+3LtNZUmy/tmCacUyuy/sgV7VgOJt
z8NV4k7LKuxSyRMEevE52fGDkXTIJJH6C+utuSN2tV4Ic8O7L4i0GaDzKvofP/I5
AWcW7dbZWAAuA+OqOYjLWZHAvNiKtGLq23JdtA3/A9YFi6FmE0fC6tj8Jg==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFFjCCAv6gAwIBAgIRAJErCErPDBinU/bWLiWnX1owDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMjAwOTA0MDAwMDAw
WhcNMjUwOTE1MTYwMDAwWjAyMQswCQYDVQQGEwJVUzEWMBQGA1UEChMNTGV0J3Mg
RW5jcnlwdDELMAkGA1UEAxMCUjMwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEK
AoIBAQC7AhUozPaglNMPEuyNVZLD+ILxmaZ6QoinXSaqtSu5xUyxr45r+XXIo9cP
R5QUVTVXjJ6oojkZ9YI8QqlObvU7wy7bjcCwXPNZOOftz2nwWgsbvsCUJCWH+jdx
sxPnHKzhm+/b5DtFUkWWqcFTzjTIUu61ru2P3mBw4qVUq7ZtDpelQDRrK9O8Zutm
NHz6a4uPVymZ+DAXXbpyb/uBxa3Shlg9F8fnCbvxK/eG3MHacV3URuPMrSXBiLxg
Z3Vms/EY96Jc5lP/Ooi2R6X/ExjqmAl3P51T+c8B5fWmcBcUr2Ok/5mzk53cU6cG
/kiFHaFpriV1uxPMUgP17VGhi9sVAgMBAAGjggEIMIIBBDAOBgNVHQ8BAf8EBAMC
AYYwHQYDVR0lBBYwFAYIKwYBBQUHAwIGCCsGAQUFBwMBMBIGA1UdEwEB/wQIMAYB
Af8CAQAwHQYDVR0OBBYEFBQusxe3WFbLrlAJQOYfr52LFMLGMB8GA1UdIwQYMBaA
FHm0WeZ7tuXkAXOACIjIGlj26ZtuMDIGCCsGAQUFBwEBBCYwJDAiBggrBgEFBQcw
AoYWaHR0cDovL3gxLmkubGVuY3Iub3JnLzAnBgNVHR8EIDAeMBygGqAYhhZodHRw
Oi8veDEuYy5sZW5jci5vcmcvMCIGA1UdIAQbMBkwCAYGZ4EMAQIBMA0GCysGAQQB
gt8TAQEBMA0GCSqGSIb3DQEBCwUAA4ICAQCFyk5HPqP3hUSFvNVneLKYY611TR6W
PTNlclQtgaDqw+34IL9fzLdwALduO/ZelN7kIJ+m74uyA+eitRY8kc607TkC53wl
ikfmZW4/RvTZ8M6UK+5UzhK8jCdLuMGYL6KvzXGRSgi3yLgjewQtCPkIVz6D2QQz
CkcheAmCJ8MqyJu5zlzyZMjAvnnAT45tRAxekrsu94sQ4egdRCnbWSDtY7kh+BIm
lJNXoB1lBMEKIq4QDUOXoRgffuDghje1WrG9ML+Hbisq/yFOGwXD9RiX8F6sw6W4
avAuvDszue5L3sz85K+EC4Y/wFVDNvZo4TYXao6Z0f+lQKc0t8DQYzk1OXVu8rp2
yJMC6alLbBfODALZvYH7n7do1AZls4I9d1P4jnkDrQoxB3UqQ9hVl3LEKQ73xF1O
yK5GhDDX8oVfGKF5u+decIsH4YaTw7mP3GFxJSqv3+0lUFJoi5Lc5da149p90Ids
hCExroL1+7mryIkXPeFM5TgO9r0rvZaBFOvV2z0gp35Z0+L4WPlbuEjN/lxPFin+
HlUjr8gRsI3qfJOQFy/9rKIJR0Y/8Omwt/8oTWgy1mdeHmmjk7j1nYsvC9JSQ6Zv
MldlTTKB3zhThV1+XWYp6rjd5JW1zbVWEkLNxE7GJThEUG3szgBVGP7pSWTUTsqX
nLRbwHOoq7hHwg==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFYDCCBEigAwIBAgIQQAF3ITfU6UK47naqPGQKtzANBgkqhkiG9w0BAQsFADA/
MSQwIgYDVQQKExtEaWdpdGFsIFNpZ25hdHVyZSBUcnVzdCBDby4xFzAVBgNVBAMT
DkRTVCBSb290IENBIFgzMB4XDTIxMDEyMDE5MTQwM1oXDTI0MDkzMDE4MTQwM1ow
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwggIiMA0GCSqGSIb3DQEB
AQUAA4ICDwAwggIKAoICAQCt6CRz9BQ385ueK1coHIe+3LffOJCMbjzmV6B493XC
ov71am72AE8o295ohmxEk7axY/0UEmu/H9LqMZshftEzPLpI9d1537O4/xLxIZpL
wYqGcWlKZmZsj348cL+tKSIG8+TA5oCu4kuPt5l+lAOf00eXfJlII1PoOK5PCm+D
LtFJV4yAdLbaL9A4jXsDcCEbdfIwPPqPrt3aY6vrFk/CjhFLfs8L6P+1dy70sntK
4EwSJQxwjQMpoOFTJOwT2e4ZvxCzSow/iaNhUd6shweU9GNx7C7ib1uYgeGJXDR5
bHbvO5BieebbpJovJsXQEOEO3tkQjhb7t/eo98flAgeYjzYIlefiN5YNNnWe+w5y
sR2bvAP5SQXYgd0FtCrWQemsAXaVCg/Y39W9Eh81LygXbNKYwagJZHduRze6zqxZ
Xmidf3LWicUGQSk+WT7dJvUkyRGnWqNMQB9GoZm1pzpRboY7nn1ypxIFeFntPlF4
FQsDj43QLwWyPntKHEtzBRL8xurgUBN8Q5N0s8p0544fAQjQMNRbcTa0B7rBMDBc
SLeCO5imfWCKoqMpgsy6vYMEG6KDA0Gh1gXxG8K28Kh8hjtGqEgqiNx2mna/H2ql
PRmP6zjzZN7IKw0KKP/32+IVQtQi0Cdd4Xn+GOdwiK1O5tmLOsbdJ1Fu/7xk9TND
TwIDAQABo4IBRjCCAUIwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAQYw
SwYIKwYBBQUHAQEEPzA9MDsGCCsGAQUFBzAChi9odHRwOi8vYXBwcy5pZGVudHJ1
c3QuY29tL3Jvb3RzL2RzdHJvb3RjYXgzLnA3YzAfBgNVHSMEGDAWgBTEp7Gkeyxx
+tvhS5B1/8QVYIWJEDBUBgNVHSAETTBLMAgGBmeBDAECATA/BgsrBgEEAYLfEwEB
ATAwMC4GCCsGAQUFBwIBFiJodHRwOi8vY3BzLnJvb3QteDEubGV0c2VuY3J5cHQu
b3JnMDwGA1UdHwQ1MDMwMaAvoC2GK2h0dHA6Ly9jcmwuaWRlbnRydXN0LmNvbS9E
U1RST09UQ0FYM0NSTC5jcmwwHQYDVR0OBBYEFHm0WeZ7tuXkAXOACIjIGlj26Ztu
MA0GCSqGSIb3DQEBCwUAA4IBAQAKcwBslm7/DlLQrt2M51oGrS+o44+/yQoDFVDC
5WxCu2+b9LRPwkSICHXM6webFGJueN7sJ7o5XPWioW5WlHAQU7G75K/QosMrAdSW
9MUgNTP52GE24HGNtLi1qoJFlcDyqSMo59ahy2cI2qBDLKobkx/J3vWraV0T9VuG
WCLKTVXkcGdtwlfFRjlBz4pYg1htmf5X6DYO8A4jqv2Il9DjXA6USbW1FzXSLr9O
he8Y4IWS6wY7bCkjCWDcRQJMEhg76fsO3txE+FiYruq9RUWhiF1myv4Q6W+CyBFC
Dfvp7OOGAN6dEOM4+qR9sdjoSYKEBpsr6GtPAQw4dy753ec5
-----END CERTIFICATE-----
EOM
sudo chown openldap /etc/ldap/slapd-key.pem /etc/ldap/slapd-cert.pem
sudo chgrp openldap /etc/ldap/slapd-key.pem /etc/ldap/slapd-cert.pem
sudo chmod 0640 /etc/ldap/slapd-key.pem /etc/ldap/slapd-cert.pem
cat <<EOM > /tmp/certinfo.ldif
dn: cn=config
add: olcTLSCertificateKeyFile
olcTLSCertificateKeyFile: /etc/ldap/slapd-key.pem
-
add: olcTLSCertificateFile
olcTLSCertificateFile: /etc/ldap/slapd-cert.pem
EOM
sudo ldapmodify -Y EXTERNAL -H ldapi:// -f /tmp/certinfo.ldif
sudo sed -E -i 's/(^\s*[^#].*)ldap:/\1ldaps:/g' /etc/default/slapd
sudo systemctl restart slapd
echo URI ldaps://ldap.az.starburstdata.net:636 | sudo tee -a /etc/ldap/ldap.conf
echo TLS_CACERT /etc/ssl/certs/ca-certificates.crt | sudo tee -a /etc/ldap/ldap.conf
cat <<EOM > /tmp/memberof.ldif
dn: cn=module,cn=config
cn: module
objectClass: olcModuleList
olcModuleLoad: memberof
olcModulePath: /usr/lib/ldap

dn: olcOverlay={0}memberof,olcDatabase={1}mdb,cn=config
objectClass: olcConfig
objectClass: olcMemberOf
objectClass: olcOverlayConfig
objectClass: top
olcOverlay: memberof
olcMemberOfRefint: TRUE
olcMemberOfGroupOC: groupOfNames

EOM
sudo ldapadd -H ldapi:/// -Y EXTERNAL -D 'cn=config' -f /tmp/memberof.ldif
cat <<EOM > /tmp/who.ldif
dn: ou=People,dc=az,dc=starburstdata,dc=net
objectClass: organizationalUnit
ou: People

dn: ou=Groups,dc=az,dc=starburstdata,dc=net
objectClass: organizationalUnit
ou: Groups

dn: uid=alice,ou=People,dc=az,dc=starburstdata,dc=net
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: alice
sn: Ecila
givenName: Alice
cn: Alice Ecila
displayName: Alice Ecila
uidNumber: 10000
gidNumber: 5000
userPassword: test
gecos: Alice Ecila
loginShell: /bin/bash
homeDirectory: /home/alice

dn: uid=bob,ou=People,dc=az,dc=starburstdata,dc=net
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: bob
sn: Bob
givenName: Bob
cn: Bob Bob
displayName: Bob Bob
uidNumber: 10001
gidNumber: 5000
userPassword: test
gecos: Bob Bob
loginShell: /bin/bash
homeDirectory: /home/bob

dn: uid=carol,ou=People,dc=az,dc=starburstdata,dc=net
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: carol
sn: Lorac
givenName: Carol
cn: Carol Lorac
displayName: Carol Lorac
uidNumber: 10002
gidNumber: 5001
userPassword: test
gecos: Carol Lorac
loginShell: /bin/bash
homeDirectory: /home/carol

dn: uid=starburst_service,ou=People,dc=az,dc=starburstdata,dc=net
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: starburst_service
sn: Ecivres_tsrubrats
givenName: Starburst_service
cn: Starburst_service Ecivres_tsrubrats
displayName: Starburst_service Ecivres_tsrubrats
uidNumber: 10100
gidNumber: 5001
userPassword: test
gecos: Starburst_service Ecivres_tsrubrats
loginShell: /bin/bash
homeDirectory: /home/starburst_service

dn: cn=analysts,ou=Groups,dc=az,dc=starburstdata,dc=net
objectClass: groupOfNames
cn: analysts
member: uid=alice,ou=People,dc=az,dc=starburstdata,dc=net
member: uid=bob,ou=People,dc=az,dc=starburstdata,dc=net

dn: cn=superusers,ou=Groups,dc=az,dc=starburstdata,dc=net
objectClass: groupOfNames
cn: superusers
member: uid=carol,ou=People,dc=az,dc=starburstdata,dc=net
member: uid=starburst_service,ou=People,dc=az,dc=starburstdata,dc=net

EOM
sudo ldapadd -x -w admin -D cn=admin,dc=az,dc=starburstdata,dc=net -f /tmp/who.ldif
echo finished > /tmp/finished
