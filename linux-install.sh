#!/usr/bin/bash

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
    fi
}

# get rid of interactive menu in Ubuntu 22 when build-essential is installed
sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" \
    /etc/needrestart/needrestart.conf

p "cleaning up old python build logs and working trees"
rm -rf /tmp/python*

p "updating and upgrading packages with apt-get"
sudo apt-get -y update
sudo apt-get -y upgrade

p "installing base packages necessary for brew"
sudo apt-get -y install build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils \
    tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev \
    libgdbm-compat-dev libgdbm-dev autoconf libtool git 

p "installing brew"
NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
ensure_in_profile '# Set PATH, MANPATH, etc., for Homebrew.'
ensure_in_profile 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"'
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
brew doctor

p "installing dependencies for BigBang"
brew install gcc awscli azure-cli aws-iam-authenticator helm kubectl libyaml \
    terraform gimme-aws-creds pyenv $OPENSSL jmeter

p "getting trino JDBC jarfile"
JMETERPREFIX=$(brew --prefix jmeter)
JMETERLIB=$JMETERPREFIX/libexec/lib
TRINOROOTVERSION=393
TRINOUPDATE=e.7
TRINOORIGVERSION=${TRINOROOTVERSION}e
TRINOVERSION=$TRINOROOTVERSION-$TRINOUPDATE
TRINOJDBC=trino-jdbc-$TRINOVERSION.jar
TRINOJDBCURL=https://s3.us-east-2.amazonaws.com/software.starburstdata.net/$TRINOORIGVERSION/$TRINOVERSION/trino-jdbc-$TRINOVERSION.jar
if wget $TRINOJDBCURL; then
    mv $TRINOJDBC $JMETERLIB
    rm -f ${TRINOJDBC}*
else
    RC=$?
    echo Failed to get $TRINOJDBC at $TRINOJDBCURL
    exit $RC
fi

p "determining correct versions of dependencies"
PYVERSION=3.10.5
OPENSSL="openssl@1.1"
OPENSSLPATH=$(readlink -f $(brew --prefix openssl@1.1))
OPENSSLLIB=$(readlink -f $OPENSSLPATH/lib)
OPENSSLINCLUDE=$(readlink -f $OPENSSLPATH/include)
echo "python version is $PYVERSION"
echo "OpenSSL path is $OPENSSLPATH"
echo "OPenSSL lib directory is $OPENSSLLIB"
echo "OPenSSL include directory is $OPENSSLINCLUDE"

p "setting up pyenv"
ensure_in_profile 'export PYENV_ROOT="$HOME/.pyenv"'
ensure_in_profile 'export PATH="$PYENV_ROOT/bin:$PATH"'
ensure_in_profile 'eval "$(pyenv init -)"'
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
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

p "installing python dependencies for BigBang"
pip install --upgrade jinja2 pyyaml psutil requests tabulate termcolor

p "installing BigBang"
git clone https://github.com/knurl/bigbang

p "configuring AWS profile"
aws configure

p "configuring Okta"
gimme-aws-creds -c

#pip install google-cloud-bigquery google-cloud-storage
#brew install --cask google-cloud-sdk
#az configure
#az login
#gcloud init
