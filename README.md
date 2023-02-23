# bigbang

## Disclaimer

**_NB:_** *This release does not form any part of the Starburst product. It is
not officially released by Starburst, nor is it supported by Starburst,
including by any of Starburst's Enterprise Support Agreements. It is made
publicly and freely available purely for educational purposes.*

## Important

**NB: Before you run bigbang.py:** Make sure you do the following:

- update my-vars.yaml, to specify your new setup
- write helm-creds.yaml, to provide your login credentials for the helm
  repo—see my-vars.yaml file for description of what to put in there
- add a Starburst license file, which you can get from your friendly local
  Starburst Solutions Architect!
- go through the requirements section below to make sure you have all the
  dependencies before starting

## Instructions on use

### What BigBang does

In the cloud of your choice, BigBang stands up some object storage (as a data
lake) and some databases, as well as a K8S cluster into which it installs
Starburst. You can optionally secure connections with TLS, and you can
optionally stand up LDAP to use as an identity source. You can configure with a
cluster size and machine type of your choice. AWS, Azure and GCP are all
supported.

BigBang uses Terraform to deploy the infrastructure required, and kubectl and
helm to deploy the helm charts. Both of these technologies are _declarative_
and _idempotent_, and fortunately BigBang is too. This means that:

- you declare the objective in my-vars.html, and BigBang attempts to achieve
  that objective every time you run it.

- If you change any configuration, you can simply re-run BigBang to achieve
  your new objective. You do _not_ need to stop BigBang and re-start it, just
  because you change some yaml; just run start again.

### General command-line usage

run bigbang.py -h to see how to use it.

### Logging into Starburst

For the Starburst UI, you will log in with the user _starburst_service_. If you
enable LDAP, then in addition to _starburst_service_, you will also have
_alice_, _bob_, and _carol_, all with password _test_. All users have the
password _test_.

## How to install it

### Homebrew

You will need to have Homebrew installed and python. To install Homebrew,
follow the instructions at the top of [the Homebrew page](https://brew.sh).
Once this is done, you'll have access to an executable called `brew`:

```
~/git/demosvc % which brew  
/usr/local/bin/brew
```

You now should install the following required Homebrew formulae, like this:

```
brew install awscli azure-cli aws-iam-authenticator helm kubectl \
    libyaml terraform gimme-aws-creds
```

And the following brew casks, like this:

```
brew install --cask google-cloud-sdk
```

__NB__: Some of these packages, including google-cloud-sdk, will require you to
add things to your .zshrc, .bashrc, .zprofile, .profile or other dotfiles in
order to ensure that the right binaries are in your PATH, and to ensure that
you have tab-completion on the binaries. _Make sure that you pay attention to
the messages that accompany each install_, and please install every package one
at a time.

### AWS

After the installation of `awscli`, you now need to configure it, by running
`aws configure`. You'll need to have ready your AWS Access Key ID, your AWS
Secret Access Key, your default region, and your default output format (which
should probably be json). This will create a `~/.aws` directory, containing a
`config` file with your default region and output format, and a `.credentials`
file containing your access key ID and secret access key. You'll never need to
change the `.credentials` file, but you will need to update the `config` file
if you want to work in a different region.

See [this link](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-config)
for the full instructions.

### Azure

After the installation of `azure-cli`, you now need to configure, by running
`az configure`, and you'll need to login, by running `az login`. When you log
in, it will fire up your default browser and have you log into the Azure Portal
with your Microsoft credentials. After running these commands you'll have a
`~/.azure` directory created with your settings and access tokens inside.

See [this link](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-macos)
for the full instructions.

### GCloud

After the installation of the `google-cloud-sdk` cask, you'll need to configure
it by running `gcloud init`. Once that is completed you'll have a
`~/.config/gcloud` directory with all of the configuration inside of it. You
will then need to run a `gcloud auth application-default login`.

Following this you will need to install a kubectl plugin as follows:

`gcloud components install gke-gcloud-auth-plugin`

See [this link](https://blog.petehouston.com/install-and-configure-google-cloud-sdk-using-homebrew/)
for the full instructions.

### Python

Next, you will need python 3.10.x or higher. On a Mac, the built-in ("system")
zversion of python that comes with the OS is 2.7.x, which obviously won't do.
If you type `which python`, you'll probably get `/usr/bin/python`. You can
check the version with `python -V`. You'll probably see something like this:

```
~ % which python
/usr/bin/python
~ % python -V
Python 2.7.16
```

You should _not_ attempt to remove this version of python, or you'll break some
of the system behaviour.

You can install a newer version of python using brew. However, in order to
manage all of the right packages together with the right version of python,
you'll probably find it easier to install `pyenv` with brew, and then use pyenv
to install the right version of python.

```
brew install pyenv
pyenv install 3.10.5
pyenv global 3.10.5
```

Then once you've got that installed, you should install the required python
libraries using python itself, like this:

`python -m pip install jinja2 pyyaml psutil requests tabulate termcolor \
    google-cloud-bigquery google-cloud-storage`

## Other

Bigbang makes heavy use of Unicode characters for representing useful visual
elements such as arrows and progress meters. Users are strongly advised to use
a monospace font with a full representation of Plane 0, which includes the
arrows (U+2500–U+257F) and box-drawing characters (U+2500–U+257F). I highly
recommend [Iosevka](https://en.wikipedia.org/wiki/Iosevka), which renders
beautifully.

====
