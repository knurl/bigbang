# bigbang

## Disclaimer

**_NB:_** *This release does not form any part of the Starburst product. It is
not officially released by Starburst, nor is it supported by Starburst,
including by any of Starburst's Enterprise Support Agreements. It is made
publicly and freely available purely for educational purposes.*

## Important

**NB: Before you run bigbang.py:** Make sure you do the following:

- update my-vars.yaml, to specify your new setup
- write helm-creds.yaml, to provide your login credentials for the helm repo—see
  my-vars.yaml file for description of what to put in there
- add a Starburst license file, which you can get from your friendly local
  Starburst Solutions Architect!
- go through the requirements section below to make sure you have all the
  dependencies before starting

## Usage

```
usage: bigbang.py [-h] [-c] [-e] {start,stop,restart,status,pfstart,pfstop}

Create your own Starbust demo service in AWS, Azure or GCP, starting from
nothing. It's zero to demo in 20 minutes or less. You provide the instance ID of
your VPN in my-vars.yaml, your desired CIDR and some other parameters. This
script uses terraform to set up a K8S cluster, with its own VPC/VNet and K8S
cluster, routes and peering connections, security, etc. Presto is automatically
set up and multiple databases and a data lake are set up. It's designed to allow
you to control the new setup from your laptop, without necessarily using a
bastion server—although a bastion server is also provided as a convenience. The
event logger is set up as well as Starburst Insights (running on a PostgreSQL
database).

positional arguments:
  {start,stop,restart,status,pfstart,pfstop}
			Command to issue for demo services. start/stop/restart:
			Start/stop/restart the demo environment. status: Show
			whether the demo environment is running or not. pfstart:
			Start port-forwarding from local ports to container
			ports (happens with start). pfstop: Stop port-forwarding
			from local ports to container ports.

optional arguments:
  -h, --help            show this help message and exit
  -c, --skip-cluster-start
                        Skip checking to see if cluster needs to be started
  -e, --empty-nodes     Unload k8s cluster only. Used with stop or restart.
```

## Requirements

### Homebrew

You will need to have Homebrew installed (on MacOS), (or your favourite Linux
package manager, if you're on Linux), and python. To install Homebrew, follow
the instructions at the top of [the Homebrew page](https://brew.sh). Once this
is done, you'll have access to an executable called `brew`:

```
~/git/demosvc % which brew  
/usr/local/bin/brew
```

You now should install the following required Homebrew formulae, like this:

```
brew install awscli azure-cli gscloud aws-iam-authenticator helm kubectl \
    libyaml socat terraform
```

And the following brew casks, like this:

```
brew install --cask google-cloud-sdk
```

### AWS CLI

After the installation of `awscli`, you now need to configure it, by running
`aws configure`. You'll need to have ready your AWS Access Key ID, your AWS
Secret Access Key, your default region, and your default output format (which
should probably be json). This will create a `~/.aws` directory, containing a
`config` file with your default region and output format, and a `.credentials`
file containing your access key ID and secret access key. You'll never need to
change the `.credentials` file, but you will need to update the `config` file if
you want to work in a different region.

See [this link](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-config) for the full instructions.

### Azure CLI

After the installation of `azure-cli`, you now need to configure, by running `az
configure`, and you'll need to login, by running `az login`. When you log in, it
will fire up your default browser and have you log into the Azure Portal with
your Microsoft credentials. After running these commands you'll have a
`~/.azure` directory created with your settings and access tokens inside.

### GCloud SDK

After the installation of the `gcloud`, `gsutil` and the rest of the Google
Cloud SDK, you'll need to configure it by running `gcloud init`. Once that is
completed you'll have a `~/.config/gcloud` directory with all of the
configuration inside of it.

### Python

Next, you will need python 3.8.5 or higher. On a Mac, the built-in ("system")
zversion of python that comes with the OS is 2.7.x, which obviously won't do. If
you type `which python`, you'll probably get `/usr/bin/python`. You can check
the version with `python -V`. You'll probably see something like this:

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
pyenv install 3.8.5
pyenv global 3.8.5
```

Then once you've got that installed, you should install the required python
libraries using python itself, like this:

`python -m pip install jinja2 pyyaml psutil requests`
