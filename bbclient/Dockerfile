FROM openjdk:22-jdk-slim

ARG HZ_HOME="/tmp"

ENV CLASSPATH_DEFAULT='*'

ENV LANG=C.UTF-8 \
    JAVA_TOOL_OPTIONS="-Djava.net.preferIPv4Stack=true -Dfile.encoding=UTF8" \
    JAVA_OPTS="-ea --add-modules java.se \
     --add-exports java.base/jdk.internal.ref=ALL-UNNAMED \
     --add-opens java.base/java.lang=ALL-UNNAMED \
     --add-opens java.base/sun.nio.ch=ALL-UNNAMED \
     --add-opens java.management/sun.management=ALL-UNNAMED \
     --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"

#ARG JDK_VERSION="17"
# Install
#RUN echo "Installing new packages" \
#    && microdnf -y update --nodocs \
#    && microdnf -y --nodocs --disablerepo=* --enablerepo=ubi-9-appstream-rpms --enablerepo=ubi-9-baseos-rpms \
#        --disableplugin=subscription-manager install \
#	iputils \
#    net-tools \
#    unzip \
#	java-${JDK_VERSION}-openjdk-headless

COPY out/artifacts/bbclient_jar/bbclient.jar ${HZ_HOME}
COPY lib/ ${HZ_HOME}
WORKDIR ${HZ_HOME}

CMD ["bash", "-c", "set -euo pipefail \
      && echo @@@@@@@@@@ \
      && java $JAVA_OPTS \
 -Dlogback.statusListenerClass=ch.qos.logback.core.status.NopStatusListener \
 -XX:+UseZGC \
 -cp '*' \
 -jar bbclient.jar"]
