FROM redhat/ubi9-minimal:9.3
ARG JDK_VERSION="21"

ARG HZ_HOME="/tmp"

ENV HZ_HOME="${HZ_HOME}" \
    JAVA_OPTS_DEFAULT="-Djava.net.preferIPv4Stack=true -XX:MaxRAMPercentage=80.0" \
    JAVA_OPTS="" \
    LANG=en_US.UTF-8 \
    JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF8" \
    PATH=${HZ_HOME}/bin:$PATH

# Install
RUN echo "Installing new packages" \
    && microdnf -y update --nodocs \
    && microdnf -y --nodocs --disablerepo=* --enablerepo=ubi-9-appstream-rpms --enablerepo=ubi-9-baseos-rpms \
        --disableplugin=subscription-manager install \
	iputils \
    net-tools \
    unzip \
	java-${JDK_VERSION}-openjdk-headless

COPY out/artifacts/bbclient_jar/bbclient.jar ${HZ_HOME}/
COPY jar/*.jar ${HZ_HOME}/
WORKDIR ${HZ_HOME}
ENTRYPOINT ["java","-cp","*","com.bbclient.Main"]
