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
