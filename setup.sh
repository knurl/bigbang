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

function is_ubuntu {
    echo UNAME=$unameOut
    case "$unameOut" in
	Linux*)	return 0;;
	Darwin*) return 1;;
	*) echo "Unknown arch $unameOut" && exit -1
    esac
}

if is_ubuntu; then
    HOMEBREWPATH="/home/linuxbrew/.linuxbrew"
else
    if [[ $(uname -m) == 'arm64' ]]; then
	HOMEBREWPATH="/opt/homebrew"
    else
	HOMEBREWPATH="/usr/local"
    fi
fi

p "***BIGBANG INSTALLATION STARTING***"

p "cleaning up old python build logs and working trees"
rm -rf /tmp/python*

if is_ubuntu; then
    # get rid of interactive menu in Ubuntu 22 when build-essential is installed
    sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" \
	/etc/needrestart/needrestart.conf

    p "updating and upgrading packages with apt-get"
    sudo apt-get -y update
    sudo apt-get -y upgrade

    p "installing base packages necessary for brew"
    sudo apt-get -y install build-essential libssl-dev zlib1g-dev libbz2-dev \
	libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils \
	tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev \
	libgdbm-compat-dev libgdbm-dev autoconf libtool git 
fi

echo $HOMEBREWPATH

p "installing brew"
if [ ! $(which brew) ]; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Brew is already installed"
fi

p "installing dependencies for bigbang"
brew install gcc awscli azure-cli aws-iam-authenticator helm kubectl libyaml \
    terraform gimme-aws-creds pyenv $OPENSSL universal-ctags

p "determining correct versions of dependencies"
PYVERSION=3.11.5
OPENSSL="openssl@1.1"
OPENSSLPATH=$(readlink -f $(brew --prefix openssl@1.1))
OPENSSLLIB=$(readlink -f $OPENSSLPATH/lib)
OPENSSLINCLUDE=$(readlink -f $OPENSSLPATH/include)
echo "python version is $PYVERSION"
echo "OpenSSL path is $OPENSSLPATH"
echo "OPenSSL lib directory is $OPENSSLLIB"
echo "OPenSSL include directory is $OPENSSLINCLUDE"

p "setting up pyenv"
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
ensure_in_profile '# pyenv'
ensure_in_profile 'export PYENV_ROOT="$HOME/.pyenv"'
ensure_in_profile 'export PATH="$PYENV_ROOT/bin:$PATH"'
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
python -m ensurepip --upgrade
pip install --upgrade pip

p "installing python dependencies for bigbang"
pip install --upgrade jinja2 pyyaml psutil requests tabulate termcolor mypy types-requests

#p "installing bigbang"
#if [ ! -d bigbang ]; then
#    git clone https://github.com/knurl/bigbang ~/bigbang
#else
#    echo "Bigbang already installed"
#fi

# Configure AWS
#
p "configuring AWS profile"
if [[ ! -f $HOME/.aws/config ]]; then
    echo Configuring SSO login. When prompted below...
    echo --> SSO Start URL as https://hazelcast.awsapps.com/start
    echo --> When prompted below, specify SSO Region as us-east-1
    aws configure sso
else
    echo "AWS config file already exists"
fi

# Configure Azure
#
p "configuring Azure profile"
if [[ ! -d $HOME/.config/.azure ]]; then
    az configure
    az login
else
    echo "Azure config already set up"
fi

pip install google-cloud-bigquery google-cloud-storage
brew install --cask google-cloud-sdk
gcloud components install gke-gcloud-auth-plugin
if [[ ! -d $HOME/.config/gcloud ]]; then
    gcloud init
    gcloud auth login
    gcloud auth application-default login
else
    echo "GCP config already set up"
fi

p "***BIGBANG INSTALLATION COMPLETE***"
