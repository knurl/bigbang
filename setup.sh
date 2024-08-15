#!/bin/bash

function p {
    Color_Off='\033[0m'       # Text Reset
    BPurple='\033[1;35m'      # Purple
    echo -e "${BPurple}==> $*${Color_Off}"
}

function ensure_in_profile {
    LINE=$1
    FILE=~/.profile
    if ! grep -qF -- "$LINE" "$FILE"; then
	echo Inserting "$LINE" into "$FILE"
	echo "$LINE" >> "$FILE"
    else
	echo "$FILE" already has "$LINE"
    fi
}

unameOut=$(uname -s)
echo This system is $unameOut

function is_ubuntu {
    echo This system is $unameOut
    case "$unameOut" in
	Linux*)	return 0;;
	Darwin*) return 1;;
	*) echo "Unknown arch $unameOut" && exit -1
    esac
}

if ! is_ubuntu ; then
    if [[ $(uname -m) == 'arm64' ]]; then
	HOMEBREWPATH="/opt/homebrew"
    else
	HOMEBREWPATH="/usr/local"
    fi
fi

p "***BIGBANG INSTALLATION STARTING***"

p "cleaning up old python build logs and working trees"
rm -rf /tmp/python*

if is_ubuntu ; then
    p "Ubuntu: Installing necessary packages using apt-get and snap"
    # get rid of interactive menu in Ubuntu 22 when build-essential is installed
    sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" \
        /etc/needrestart/needrestart.conf

    p "updating and upgrading packages with apt-get"
    sudo apt-get -y update
    sudo apt-get -y upgrade

    p "installing apt packages for bigbang"
    sudo apt-get -y install azure-cli python3 python3-pip

    p "Installing snap packages for bigbang"
    sudo snap install aws-cli --classic
    sudo snap install kubectl --classic
    sudo snap install helm --classic
    sudo snap install terraform --classic

    p "Installing google-cloud-cli"
    pushd /tmp
    curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz
    tar -xf google-cloud-cli-linux-x86_64.tar.gz
    ./google-cloud-sdk/install.sh -q
    popd
else
    p "installing brew"
    if [ ! $(which brew) ]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        echo "Brew is already installed"
        export PATH="$HOMEBREWPATH/bin:$PATH"
        echo $HOMEBREWPATH
    fi

    p "installing dependencies for bigbang"
    brew install gcc awscli azure-cli kubectl helm terraform pyenv $OPENSSL

    OPENSSL="openssl@3"

    OPENSSLPATH=$(readlink -f $(brew --prefix $OPENSSL))
    OPENSSLLIB=$(readlink -f $OPENSSLPATH/lib)
    OPENSSLINCLUDE=$(readlink -f $OPENSSLPATH/include)
    echo "OpenSSL path is $OPENSSLPATH"
    echo "OPenSSL lib directory is $OPENSSLLIB"
    echo "OPenSSL include directory is $OPENSSLINCLUDE"

    p "determining correct versions of dependencies"
    PYVERSION=3.11.5
    echo "python version is $PYVERSION"

    p "setting up pyenv"
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    ensure_in_profile '# pyenv'
    ensure_in_profile 'export PYENV_ROOT="$HOME/.pyenv"'
    ensure_in_profile 'export PATH="$HOMEBREWPATH/bin:$PYENV_ROOT/bin:$PATH"'
    ensure_in_profile 'eval "$(pyenv init -)"'
    p "pyenv version is $(pyenv --version)"

    p "installing python ${PYVERSION} and setting as system default version"
    export LDFLAGS="-Wl,-rpath,$OPENSSLLIB -L$OPENSSLLIB"
    export CPPFLAGS="-I$OPENSSLINCLUDE"
    export SSH=$OPENSSLPATH
    export CONFIGURE_OPTS="-with-openssl=$OPENSSLPATH"
    echo LDFLAGS=$LDFLAGS
    echo CPPFLAGS=$CPPFLAGS
    echo SSH=$SSH
    echo CONFIGURE_OPTS=$CONFIGURE_OPTS
    pyenv install -s $PYVERSION
    pyenv global $PYVERSION

    p "installing pip"
    $PYTHON -m ensurepip --upgrade
    pip install --upgrade pip
fi

p "installing python dependencies for bigbang"
pip install --upgrade jinja2 pyyaml psutil requests tabulate termcolor mypy types-requests

# Configure AWS
#
#p "configuring AWS profile"
#if [[ ! -f $HOME/.aws/config ]]; then
#    echo Configuring SSO login. When prompted below...
#    echo --> SSO Start URL as https://hazelcast.awsapps.com/start
#    echo --> When prompted below, specify SSO Region as us-east-1
#    aws configure sso
#else
#    echo "AWS config file already exists"
#fi

# Configure Azure
#
#p "configuring Azure profile"
#az configure
#az login

pip install google-cloud-bigquery google-cloud-storage
gcloud components install gke-gcloud-auth-plugin
if [[ ! -d $HOME/.config/gcloud ]]; then
    gcloud init
else
    echo "GCP config already set up"
fi

gcloud components update

p "***BIGBANG INSTALLATION COMPLETE***"

