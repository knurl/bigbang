#!/bin/bash

KEY=~/.ssh/id_rsa
STARBURSTNAME=starburst.az.starburstdata.net
SURL=https://$STARBURSTNAME
RURL=http://localhost
LOOPBACK=127.0.0.1
HOSTSFILE=/etc/hosts

BASTIONAWS=18.168.165.112
STARBURSTAWS=internal-a8f5a00e49aba4fae8f226409ad805a2-774271760.eu-west-2.elb.amazonaws.com
RANGERAWS=internal-ade8b26bbb22441ccb7908a162606530-2064642569.eu-west-2.elb.amazonaws.com

#cat <<EOM > $KEY
#-----BEGIN OPENSSH PRIVATE KEY-----
#b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn
#NhAAAAAwEAAQAAAYEAoRsO80xSbUmKHGbiI9W0s2pYtHlvxlFH1AfXOTeGnv8kHvIqvpav
#F4ee2r4LQsXGVm4VAEMfS6fa7ixgySBs71oubNgilSwYCkqQiy9KLaYvSZ61moYAGgcZ2s
#dmFjiT0MLGjWgB3wGbQvGAaWrVm5FEqT9W69L7mQK9ibmjEXyo9iYuDeVzB9aBVJ9ixrfh
#Yv9lSX4dOFK8nOUrMJ9BHBPHnezOQXtoe6ZQo4NiV9XdDl6n9yGiWzropuPbRde7bfc9h/
#K4VpIIIu7JNPO3EsuEdDB55hMmHS2RC7fohlIRd6xSDudLrF+fBzd+kY/zp9IXRIvb5qSL
#XmKmF8VobzLiLGgyTUzJRqEKmZZYuBrnKKJaz+f4vkhiLt34F+04cpI3dADucFQCTtCph5
#ArEXsfSpu7cCXmH9ObGyEP4bybSME4WpRGOMwnWoOw3EF09hRM0fQ3B0pa3L6zAi1vSaK9
#WN8cGMx/6hsL2+w5DRiqGLLMiQpcPdQFBTTvJwUPAAAFqGYoY4lmKGOJAAAAB3NzaC1yc2
#EAAAGBAKEbDvNMUm1Jihxm4iPVtLNqWLR5b8ZRR9QH1zk3hp7/JB7yKr6WrxeHntq+C0LF
#xlZuFQBDH0un2u4sYMkgbO9aLmzYIpUsGApKkIsvSi2mL0metZqGABoHGdrHZhY4k9DCxo
#1oAd8Bm0LxgGlq1ZuRRKk/VuvS+5kCvYm5oxF8qPYmLg3lcwfWgVSfYsa34WL/ZUl+HThS
#vJzlKzCfQRwTx53szkF7aHumUKODYlfV3Q5ep/chols66Kbj20XXu233PYfyuFaSCCLuyT
#TztxLLhHQweeYTJh0tkQu36IZSEXesUg7nS6xfnwc3fpGP86fSF0SL2+aki15iphfFaG8y
#4ixoMk1MyUahCpmWWLga5yiiWs/n+L5IYi7d+BftOHKSN3QA7nBUAk7QqYeQKxF7H0qbu3
#Al5h/TmxshD+G8m0jBOFqURjjMJ1qDsNxBdPYUTNH0NwdKWty+swItb0mivVjfHBjMf+ob
#C9vsOQ0YqhiyzIkKXD3UBQU07ycFDwAAAAMBAAEAAAGAfpHjjQHJQFMmTmoGAGFFNi+2wR
#Mm3Ye+BraiQDF/cirBFg7rxhBcPwAtrWzhK/R1fjG+Dhat36JgPf5fi6QN8X3IO3sSsF+U
#A4HRTYg5nuORAyXNRzk/mzM4/MjrS0nn13suwqmTzsBUWqOhXzCv4Sif6Nf6UgvP3sZoYm
#uV0Yc+tyQHyqMZXG8J7JHL6JNOX5iG2tZZ3oYh6KGi7PAxFv3zNf91i7yIuZxQfiYafSdo
#JIH5NA8YntQJNBSPkK+LMfLSS5XV6eVCCklWDCa2un6NWtH3i4SZsAnhzh9LS4n9WI7wHz
#vY9CmV8KUzTFQzXHws/7PPzeCFgeKHfcNKRarFRV60unspcUOgPBk8BtuGCqKCHoq31AsI
#4B137qjtP2SYiCwb+F9brZZ+FP4Ja04uU2pLI3IBG1ajRtTfixXpKTe23ytkqOG0PM3dyY
#VY2VVx+HvsWzmpTq8HznE6fr1qzdifrEPYTzd0BCXz0nCBMQOAVhT7gN7De8VuJiEBAAAA
#wQCxh9/ZlWb4AQCPKiH0Nmv8rDh/+cWVPQrcK3BSE6R2k+W/PWydTQ2Y56YrKeXRpn51Nr
#F/uOSQ5Z+L/7NPAQwhxvvAqPEuVLv4kfDXKedhNo+KT+CaVl5n51w7SjLlQOOl3PZ+Ktvl
#BcbQYPNXxkhZJhwQyqTtJZqzaJrnZIeYBYiuUXtniGHQXukqAJJcDanNBexn2v8y9Qh0Iq
#v03TJ0Vm1izd3o9TVJyhIAtfhx7hoigK294ewrB9jO6iottnsAAADBANHjWsEK8mxMxEEi
#Sw7myP0bM51anA99gMwgul+DMEsw2a7sZc5LgJLoNNSRtrzJRiUMeHZYzwL4gG6BljVNGt
#EKEkddoE+AxAA64trNHcAe/qBB6jEhxdkjw44r5aVKXyRVWOGRl2m7mKShuoEoyW+UV5AN
#FU/lSUzChW0OLgsmdv6hTXFNNDD5EIuUSD5jXxs+R3SUuRABA49RuH5jQkYoU0Au3hPfqf
#sdgbV1kMuxnEPkmdSKRLKxKp34pS5yIwAAAMEAxIAOYTJiy0TjOl0eGfmBQDkbabFXFrkZ
#rcpnLge5xKZYOpuaj5/PUNKII2XM/pVbVGUn0L22fKZgrsPmMpryuWu9rSz3YAt759Nfl6
#2+jE/aBgb1oHXmDbNaKDi25vAI/uosycfIII1+cXOb6kL0R+PJ8sIMC0PFpewFJUhPTX2J
#9kWgBKHmfnw7aPA7J8vGyUNt09ZRx12vFkEc5ODiJ6Ke3QHLweynYU78QBwB3pOqOVYliA
#EJ6TIbBu7BZsIlAAAAL3JvYkBpcC0xOTItMTY4LTEtMTAyLmV1LXdlc3QtMy5jb21wdXRl
#LmludGVybmFsAQID
#-----END OPENSSH PRIVATE KEY-----
#EOM
#chmod 600 $KEY

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
