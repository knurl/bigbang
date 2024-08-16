#!/bin/bash

function p {
    Color_Off='\033[0m'       # Text Reset
    BPurple='\033[1;35m'      # Purple
    echo -e "${BPurple}==> $*${Color_Off}"
}

function ensure_in_file {
    LINE=$1
    FILE=$2
    if ! grep -qF -- "$LINE" "$FILE"; then
	echo Inserting "$LINE" into "$FILE"
	echo "$LINE" >> "$FILE"
    else
	echo "$FILE" already has "$LINE"
    fi
}

function ensure_in_profile {
    ensure_in_file $1 ~/.profile
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

PYVERSION=3.11
echo "python version is $PYVERSION"

if is_ubuntu ; then
    #
    ##########
    # Ubuntu #
    ##########
    #
    p "Ubuntu: Installing necessary packages using apt-get and snap"
    # get rid of interactive menu in Ubuntu 22 when build-essential is installed
    sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" \
        /etc/needrestart/needrestart.conf

    p "updating and upgrading packages with apt-get"
    sudo apt-get -y update
    sudo apt-get -y upgrade

    p "installing apt packages for bigbang"
    sudo apt-get install -y azure-cli

    p "Installing snap packages for bigbang"
    sudo snap install aws-cli --classic
    sudo snap install kubectl --classic
    sudo snap install helm --classic
    sudo snap install terraform --classic

    p "Installing google-cloud-cli"

    # First, remove any gcloud installation done by snap
    sudo snap remove gcloud-cloud-cli

    # Now install it without a package manager
    GCLOUDINSTALLDIR=$HOME/gcloud-sdk
    GCLOUDDIR=$GCLOUDINSTALLDIR/google-cloud-sdk
    mkdir -p $GCLOUDINSTALLDIR
    pushd $GCLOUDINSTALLDIR
    curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz
    tar -xf google-cloud-cli-linux-x86_64.tar.gz
    ./google-cloud-sdk/install.sh -q
    ensure_in_file "source $GCLOUDDIR/completion.bash.inc" ~/.bashrc
    ensure_in_file "source $GCLOUDDIR/path.bash.inc" ~/.bashrc
    ensure_in_file "source $GCLOUDDIR/completion.zsh.inc" ~/.zshrc
    ensure_in_file "source $GCLOUDDIR/path.zsh.inc" ~/.zshrc
    popd

    p "installing Python $PYVERSION"
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get install -y python3.11
    sudo apt-get install -y python3.11-venv

else

    #
    #########
    # MacOS #
    #########
    #
    p "installing brew"
    if [ ! $(which brew) ]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        echo "Brew is already installed"
        export PATH="$HOMEBREWPATH/bin:$PATH"
        echo $HOMEBREWPATH
    fi

    p "installing dependencies for bigbang"
    brew install gcc awscli azure-cli kubectl helm terraform $OPENSSL python@3.11

    OPENSSL="openssl@3"

    OPENSSLPATH=$(readlink -f $(brew --prefix $OPENSSL))
    OPENSSLLIB=$(readlink -f $OPENSSLPATH/lib)
    OPENSSLINCLUDE=$(readlink -f $OPENSSLPATH/include)
    echo "OpenSSL path is $OPENSSLPATH"
    echo "OPenSSL lib directory is $OPENSSLLIB"
    echo "OPenSSL include directory is $OPENSSLINCLUDE"
fi

p "setting up Python $PYVERSION virtual environment"
python3.11 -m venv .venv # automatically also installs pip
source .venv/bin/activate

p "installing python dependencies for bigbang"
pip install --upgrade jinja2 pyyaml psutil requests tabulate \
    termcolor mypy types-requests

#
# Configure AWS
#
p "configuring AWS profile"
if [[ ! -f $HOME/.aws/config ]]; then
    echo Configuring SSO login. When prompted below...
    echo SSO Start URL as https://hazelcast.awsapps.com/start
    echo When prompted below, specify SSO Region as us-east-1
    aws configure sso
else
    echo "AWS config file already exists"
fi

#
# Configure Azure
#
p "configuring Azure profile"
if [[ ! -d $HOME/.azure ]]; then
    az configure
    az login
else
    echo "Azure config files already exist"
fi

# 
# Configure GCP
#
pip install google-cloud-bigquery google-cloud-storage
source ~/.bashrc
gcloud components update
gcloud components install gke-gcloud-auth-plugin --quiet
if [[ ! -d $HOME/.config/gcloud ]]; then
    gcloud init
    gcloud auth application-default login
else
    echo "GCP config files already exist"
fi

p "***BIGBANG INSTALLATION COMPLETE***"

