#!/bin/sh
#
#  only doing all the sudos as cloud-init doesn't run as root, likely better to use Azure VM Extensions
#

touch /tmp/forwarderSetup_start

#  Install Bind9
#  https://www.digitalocean.com/community/tutorials/how-to-configure-bind-as-a-caching-or-forwarding-dns-server-on-ubuntu-14-04
sudo apt-get update -y
sudo apt-get install bind9 -y

# configure Bind9 for forwarding
sudo cat > named.conf.options << EndOFNamedConfOptions
acl goodclients {
    172.31.0.0/16;
    172.16.0.0/16;
    192.168.0.0/16;
    10.0.0.0/8;
    localhost;
    localnets;
};

options {
        directory "/var/cache/bind";

        recursion yes;

        allow-query { goodclients; };

	forwarders {
	    168.63.129.16;
	};
        forward only;

	dnssec-enable no;
        dnssec-validation no;

        auth-nxdomain no;    # conform to RFC1035
        listen-on { any; };
};
EndOFNamedConfOptions

sudo cp named.conf.options /etc/bind
sudo service bind9 restart

touch /tmp/forwarderSetup_end
