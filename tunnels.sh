#!/bin/bash

KEY=~/.ssh/id_rsa
STARBURSTNAME=starburst.az.starburstdata.net
SURL=https://$STARBURSTNAME
RURL=http://localhost
LOOPBACK=127.0.0.1
HOSTSFILE=/etc/hosts

BASTIONAWS=35.177.21.209
STARBURSTAWS=internal-aecda6f7a0a934faaa251e7eae410f59-1264212871.eu-west-2.elb.amazonaws.com
RANGERAWS=internal-a49d2b3ab464b41f2bde6cd4d3c740f3-1714724636.eu-west-2.elb.amazonaws.com

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
PIDS=$(ps -ef | grep -E "ssh.*-N -L.*ubuntu@$BASTIONAWS" | grep -v grep | awk '{print $2}' ORS=' ')
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

echo Adding hosts to known hosts
ssh-keyscan -4 -p22 -H $BASTIONAWS 2>&1 >> ~/.ssh/known_hosts

echo Host keys are now stored in ~/.ssh/known_hosts

# AWS Starburst
echo "Starting AWS Starburst tunnel to $SURL:8443 (you can go here now)"
ssh -i $KEY -N -L8443:$STARBURSTAWS:8443 ubuntu@$BASTIONAWS &
PIDS="$PIDS $!"

# AWS Ranger
echo "Starting AWS Ranger tunnel to $RURL:6080 (you can go here now)"
ssh -i $KEY -N -L6080:$RANGERAWS:6080 ubuntu@$BASTIONAWS &
PIDS="$PIDS $!"

echo Tunnel PIDs are $PIDS
echo ***HIT ENTER TO KILL ALL TUNNELS***
read
kill $PIDS
