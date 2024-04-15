#!/bin/zsh

cb=$(which certbot)
if [[ ! -x $cb ]]; then
    echo "Is certbot installed?"
    exit
fi

CERTDIR=~/letsencrypt
DOMAIN=az.starburstdata.net
STARBURST=starburst.$DOMAIN
LDAP=ldap.$DOMAIN
CERTS=($STARBURST $LDAP)
LIVE=$CERTDIR/live
PASSWD=test123
FULLCERT=fullcert.pem
PKCS12=fullchain.pkcs12
KEYSTORE=fullchain.jks
BIGBANGCERT=~/git/bigbang/certs

mkdir -p $CERTDIR
OPTIONS="certonly --preferred-challenges=dns --manual --config-dir $CERTDIR --work-dir $CERTDIR --logs-dir $CERTDIR --email rob@starburst.io --no-eff-email --agree-tos"

for cert in $CERTS; do
    echo "======= BEGINNING PROCESSING OF CERT $cert ======="
    certbot ${=OPTIONS} -d $cert
    pushd $LIVE/$cert
    cat cert.pem > $FULLCERT
    cat chain.pem >> $FULLCERT
    cat fullchain.pem >> $FULLCERT
    cat privkey.pem >> $FULLCERT
    openssl pkcs12 -export -out $PKCS12 -in $FULLCERT -password pass:$PASSWD
    keytool -v -importkeystore -srckeystore $PKCS12 -destkeystore $KEYSTORE -deststoretype JKS -srcstorepass $PASSWD -deststorepass $PASSWD
    popd
    echo "======= ENDING PROCESSING OF CERT $cert ======="
done

for cert in $CERTS; do
    echo "======= TRANSFERRING CERT $cert ======="
    rm -rf $BIGBANGCERT/$cert
    cp -LRf $LIVE/$cert $BIGBANGCERT/$cert
done
