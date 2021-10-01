#!/bin/bash

KEY=~/.ssh/bigdata-london.key
STARBURSTNAME=starburst.az.starburstdata.net
SURL=https://$STARBURSTNAME
RURL=http://localhost
LOOPBACK=127.0.0.1
HOSTSFILE=/etc/hosts

BASTIONAWS=13.37.96.98
STARBURSTAWS=internal-a554dbe6c992842b5a53f634398f0a27-1597890617.eu-west-3.elb.amazonaws.com
RANGERAWS=internal-ad67256b5949249b4a3f79e4f0607908-753428237.eu-west-3.elb.amazonaws.com

BASTIONAZU=20.199.118.180
STARBURSTAZU=10.4.0.103
RANGERAZU=10.4.0.104

BASTIONGCP=35.205.181.188
STARBURSTGCP=172.20.208.103
RANGERGCP=172.20.208.104

cat <<EOM > $KEY
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABFwAAAAdzc2gtcn
NhAAAAAwEAAQAAAQEAt0PV1TiGj1uCxz9EHGphzafB/w4WpTKr6/H4rKoJfRO8HOTfW4d0
+TC8cR14ko3enZ8RqbzvDkOesCkzLxDxvt5ilv1AeB3cEndcAowz+BUv2WUMi8XW4PU5mV
bIjk0KN3es3ecciRv+1gF4p2OEfauRbwmQ2uSJxK+7fc5fEKZNqR6XoNjeZcDZyEAvxRbo
m1X9h4xjASVMVpy+7OyJWAjGBg9F9BKVsebUl5xksqADRkyM07FDioAYGP7+/lPruj9om4
FylrcgWaZTVa4rbBdsmuMo2dksZyYEJiPWhtwvzEweF9uTpXC4tSeQzXcLnBJyff9GM8XL
b/ONgvuuswAAA9D5Cf8T+Qn/EwAAAAdzc2gtcnNhAAABAQC3Q9XVOIaPW4LHP0QcamHNp8
H/DhalMqvr8fisqgl9E7wc5N9bh3T5MLxxHXiSjd6dnxGpvO8OQ56wKTMvEPG+3mKW/UB4
HdwSd1wCjDP4FS/ZZQyLxdbg9TmZVsiOTQo3d6zd5xyJG/7WAXinY4R9q5FvCZDa5InEr7
t9zl8Qpk2pHpeg2N5lwNnIQC/FFuibVf2HjGMBJUxWnL7s7IlYCMYGD0X0EpWx5tSXnGSy
oANGTIzTsUOKgBgY/v7+U+u6P2ibgXKWtyBZplNVritsF2ya4yjZ2SxnJgQmI9aG3C/MTB
4X25OlcLi1J5DNdwucEnJ9/0Yzxctv842C+66zAAAAAwEAAQAAAQAZca6fkuCDyNXIag0/
0LlRf0gc7EzSlM1vzcGT32u/1NyaOmCUaaMg8dZH8iqKVm4g/jPKmDOsjFDc7mtvzm9x65
hOlEy+II8sdSvuIp8Yg4CIM1JhmY8y3nknw/fGYgXYG6KBkJPSqXNhLQUeYF/FvutLOk3F
RlOmXiuu1Nc4DVKmgwPO+HftNaExXWY0SCvK4Y1iUZrNaD4IA2UGJmppLv1GFXU13R4xB+
K4z95R7pbPPv+WS06iLKDpY+Ps9TdJf+k/l3tY5ZNEKPCRWO9QiuGZuNmgfih4/HfAW1j+
smsbOn35GJtGnC4mQuXOy7STd09q/JSZI6NHNZtJnDEBAAAAgB5jqRKSaDS9blqU0nAaDW
qWiDwDeY9HAc6TuJbcDiyt5P8lsmc6f5ZZm5UY4P1PN9I9pxr/te7Tgiek+PaVhlPFPi88
syKHDXt8UXlhEZJi/DrjIUYQwPNBjM5XFmYBHBybQSyR6tfCcQf9j4ZmHSfYP9up8QAH8k
do8Ip5jnMOAAAAgQDjFP8Z/GBYdg3AbgcgbV1vvRqPEKaoHlzFc2JtGVPXKyfGaxgAtPnY
C/vJ4M8nztfHNymSL/Iynul5brYtangaycnh0fIFpad94xnXiOaHP1ejR5E+xYuYyMGQgc
sutPCoLcrdzYGKE3hCPtqVuzJtFQbwZoLvYv4hcc1OCt2mMwAAAIEAzppg3g+2pegdm07W
9yfUB4n8g6dYmgYem4gO/aGlANoYNuqm0wmhiAv9VicD9OXlFIi9yEUTP3hXFrA5+48n+H
oW+NUTNh/EbN+ZUh+8Vy8il6Z5Z/IKa2G0+zqyXje6lJlse1t4NzomBR8/88sEETNnJaHE
4fqcJ9hBPlZ0VYEAAAAWcm9iQFN0YXJidXJzdE1hYy5sb2NhbAECAwQF
-----END OPENSSH PRIVATE KEY-----
EOM
chmod 600 $KEY

# Modify /etc/hosts to include an entry for Starburst
grep -q $STARBURSTNAME $HOSTSFILE 2>&1 > /dev/null
if [ $? -eq 1 ]; then
    echo I need your root password here so I can modify your /etc/hosts
    echo We need to add the starburst DNS name for the certs to work
    echo "$LOOPBACK $STARBURSTNAME" | sudo tee -a $HOSTSFILE
    echo ...was added to your $HOSTSFILE
fi

# This line picks up all the existing processes that looks like tunnels. They
# will be killed by the time you hit Enter, by the final kill statement below.
PIDS=$(ps -ef | grep -E 'ssh -i.*bigdata-london.key -N.*ubuntu@' | grep -v grep | awk '{print $2}' ORS=' ')
if [ -n "$PIDS" ]; then
    echo Killing existing tunnels $PIDS...
    kill $PIDS
    PIDS=""
fi

echo On Mac Terminal, you can highlight the URLs below with your trackpad,
echo right-click on the highlighted URL, and go it by clicking 'Open URL'!
echo Also note: If you get 'Address already in use', just run the script
echo again and hit Enter, and it will kill all the existing PIDs.

echo Removing old host keys
touch ~/.ssh/known_hosts
ssh-keygen -q -R $BASTIONAWS 2>&1 > /dev/null
ssh-keygen -q -R $BASTIONAZU 2>&1 > /dev/null
ssh-keygen -q -R $BASTIONGCP 2>&1 > /dev/null

echo Adding hosts to known hosts
ssh-keyscan -4 -p22 -H $BASTIONAWS 2>&1 >> ~/.ssh/known_hosts
ssh-keyscan -4 -p22 -H $BASTIONAZU 2>&1 >> ~/.ssh/known_hosts
ssh-keyscan -4 -p22 -H $BASTIONGCP 2>&1 >> ~/.ssh/known_hosts

echo Host keys are now stored in ~/.ssh/known_hosts

# AWS Starburst
echo Starting AWS Starburst tunnel to $SURL:8443/ui/insights
ssh -i $KEY -N -L8443:$STARBURSTAWS:8443 ubuntu@$BASTIONAWS &
PIDS="$PIDS $!"

# AWS Ranger
echo Starting AWS Ranger tunnel to $RURL:6080
ssh -i $KEY -N -L6080:$RANGERAWS:6080 ubuntu@$BASTIONAWS &
PIDS="$PIDS $!"

# Azure Starburst
echo Starting Azure Starburst tunnel to $SURL:8444/ui/insights
ssh -i $KEY -N -L8444:$STARBURSTAZU:8443 ubuntu@$BASTIONAZU &
PIDS="$PIDS $!"

# Azure Ranger
echo Starting Azure Ranger tunnel to $RURL:6081
ssh -i $KEY -N -L6081:$RANGERAZU:6080 ubuntu@$BASTIONAZU &
PIDS="$PIDS $!"

# GCP Starburst
echo Starting GCP Starburst tunnel to $SURL:8445/ui/insights
ssh -i $KEY -N -L8445:$STARBURSTGCP:8443 ubuntu@$BASTIONGCP &
PIDS="$PIDS $!"

# GCP Ranger
echo Starting GCP Ranger tunnel to $RURL:6082
ssh -i $KEY -N -L6082:$RANGERGCP:6080 ubuntu@$BASTIONGCP &
PIDS="$PIDS $!"

echo Tunnel PIDs are $PIDS
echo ***HIT ENTER TO KILL ALL TUNNELS***
read
kill $PIDS
