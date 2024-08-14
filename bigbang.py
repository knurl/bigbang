#!/usr/bin/env python

#import pdb
import os
import hashlib
import argparse
import sys
import textwrap
import requests
import json
import re
import subprocess
import ipaddress
import glob
import random
import yaml # type: ignore
import psutil # type: ignore
import time
import string
import socket
from threading import Thread
from datetime import datetime
from contextlib import ExitStack

from subprocess import CalledProcessError
from typing import List, Callable, Optional, Any, Dict
from urllib.parse import urlparse
import jinja2
from jinja2.meta import find_undeclared_variables

import logging

# local imports
import out
import bbio
import ready # local imports
from cmdgrp import CommandGroup
from capcalc import HazelcastContainers, ChaosMeshContainers
from run import runShell, runTry, runStdout, runCollect, retryRun, runIgnore
from timer import Timer

# Do this just to get rid of the warning when we try to read from the
# api server, and the certificate isn't trusted
import urllib3 # type: ignore
urllib3.disable_warnings()

# Suppress info-level messages from the requests library
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

#
# Global variables.
#

# Paths or path sub-components
templatedir = bbio.where("templates")
tmpdir      = "/tmp"
rsa         = os.path.expanduser("~/.ssh/id_rsa")
rsaPub      = os.path.expanduser("~/.ssh/id_rsa.pub")
knownhosts  = os.path.expanduser("~/.ssh/known_hosts")
myvarsbf    = 'my-vars.yaml'
myvarsf     = bbio.where(myvarsbf)
sfdccredsbf = 'sfdc-creds.yaml' # don't find FQP yet as SFDC is optional
tfvars      = "variables.tf" # basename only, no path!
hostsf      = "/etc/hosts"

# Different cloud targets
clouds = ("aws", "az", "gcp")

# Hosts, ports, services and associated creds
dbports        = { "mysql": 3306, "postgres": 5432 }
localhost      = "localhost"
localhostip    = "127.0.0.1"
domain         = "hazelcast.net" # cannot terminate with .; Azure will reject
srvnm_cluster  = 'dev'
srvnm_bbclient = 'bbclient'
bbclientpodsel = 'app=bbclient'
devpodsel      = 'app.kubernetes.io/instance=dev'
depnm_bbclient = 'deployment/bbclient-depl'
ssnm_dev       = 'statefulset/dev'
bastionuser    = 'ubuntu'
dns_bbclient   = srvnm_bbclient + domain

# K8S / Helm
hz_namespace    = "hazelcast"
chaos_namespace = "chaos-mesh"
kube            = "kubectl"
helm            = "helm"
minNodes        = 3
maxpodpnode     = 32
maxloggedcns    = 32

#
# Secrets
# 
secretsbf    = "secrets.yaml"
secretsf     = bbio.where(secretsbf)

#
# Start of execution. Handle commandline args.
#

p = argparse.ArgumentParser()
p.add_argument('-c', '--skip-cluster-start', action="store_true",
               help="Skip checking to see if cluster needs to be started.")
p.add_argument('-e', '--empty-nodes', action="store_true",
               help="Unload k8s cluster only. Used with stop.")
p.add_argument('-g', '--target', action="store",
               help="Force cloud target to specified value.")
p.add_argument('-t', '--test', action='store_true',
               help='Run in chaos testing mode')
p.add_argument('-z', '--zone', action="store",
               help="Force zone/region to specified value.")
p.add_argument('command',
               choices = ['start', 'stop'],
               help="""Start/stop the demo environment.""")
p.add_argument('-P', '--progmeter-test', action="store_true",
               help=argparse.SUPPRESS)

ns = p.parse_args()

# Options which can only be used with stop
if ns.command != 'stop' and ns.empty_nodes:
    p.error("empty_nodes is only used with stop")

# Options which can only be used with start
if ns.command != 'start':
    v = vars(ns)
    for switch in {'skip_cluster_start', 'test'}:
        if switch in v and v[switch]:
            p.error(f"{switch} is only used with start")

#
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd config file,
# very small, called ./helm-creds.yaml, which contains just the username and
# password for the helm repo you wish to use to get the helm charts.
#
targetlabel      = 'Target'
prefzonelabel    = 'PreferredZones'
nk8snodeslabel   = 'NodeCount'
nhzmemberslabel  = 'HzMemberCount'
nhzclientslabel  = 'HzClientCount'
appversionlabel  = 'AppVersion'
oprchartvlabel   = 'OperatorChartVersion'
chaoschartvlabel = 'ChaosMeshChartVersion'
tlscoordlabel    = 'RequireCoordTls'

try:
    with open(myvarsf) as mypf:
        myvars = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read user variables file {e}")

def requireKey(key: str, d: dict[str, Any]):
    if key not in d:
        raise KeyError(key)

try:
    # Email
    email = myvars['Email']

    # Target
    target = ns.target if ns.target else myvars[targetlabel]

    # Zone - If from myvars, take first choice from preferred list
    zone = ns.zone if ns.zone else myvars[prefzonelabel][target][0]

    appversion        = myvars[appversionlabel] # AppVersion
    oprchartversion   = myvars[oprchartvlabel] # OprChartVersion
    nk8snodes         = myvars[nk8snodeslabel] # NodeCount
    nhzmembers        = myvars[nhzmemberslabel] # HzNodeCount
    nhzclients        = myvars[nhzclientslabel] # HzClientCount
    tlscoord          = myvars[tlscoordlabel] # RequireCoordTls

    requireKey("AwsInstanceTypes", myvars)
    requireKey("AwsSmallInstanceType", myvars)
    requireKey("AzureVmTypes", myvars)
    requireKey("AzureSmallVmType", myvars)
    requireKey("GcpMachineTypes", myvars)
    requireKey("GcpSmallMachineType", myvars)

    hz_helm_repo_name        = myvars["HzHelmRepo"]
    hz_helm_repo_location    = myvars["HzHelmRepoLocation"]

    if ns.test:
        chaoschartversion        = myvars[chaoschartvlabel]
        chaos_helm_repo_name     = myvars["ChaosHelmRepo"]
        chaos_helm_repo_location = myvars["ChaosHelmLocation"]
except KeyError as e:
    print(f"Unspecified configuration parameter {e} in {myvarsf}.")
    sys.exit(f"Consider running a git diff {myvarsf} to ensure no "
             "parameters have been eliminated.")

#
# Email
#
# Verify the email looks right, and extract username from it.
emailparts = email.split('@')
if not (len(emailparts) == 2 and "." in emailparts[1]):
    sys.exit(f"Email specified in {myvarsf} must be a full email address.")
# Google requires labels to follow RFC-1035 (which is used for DNS names).
# Amazon and Azure tags are more forgiving, so allow more special chars.
validchars = r"a-zA-Z0-9"
if target in ("aws", "az"):
    validchars += r"._/=+\-"
invalidchars = r'[^' + validchars + r']'
username = re.sub(invalidchars, "-", emailparts[0]).lower()

#
# Target, Zone
#
# Set the region and zone from the location. We assume zone is more precise and
# infer the region from the zone.
def getRegionFromZone(zone: str) -> str:
    region = zone
    if target == "gcp":
        assert re.fullmatch(r"-[a-e]", zone[-2:])
        region = zone[:-2]

    # Azure and GCP assume the user is working potentially with multiple
    # locations. On the other hand, AWS assumes a single region in the config
    # file, so make sure that the region in the AWS config file and the one set
    # in my-vars are consistent, just to avoid accidents.
    if target == "aws":
        awsregion = runCollect("aws configure get region".split())
        if awsregion != region:
            sys.exit(textwrap.dedent(f"""\
                    Region {awsregion} specified in your config doesn't match
                    region {region} set in your {myvarsf} file. Cannot
                    continue. Please ensure these match and re-run."""))

    return region

region = getRegionFromZone(zone)

# Terraform files are in a directory named for target
tfdir = bbio.where(target)
tf    = f"terraform -chdir={tfdir}"
for d in [templatedir, tmpdir, tfdir]:
    assert bbio.writeableDir(d)

#
# NodeCount
#
if nk8snodes <= nhzmembers:
    sys.exit(f'To accommodate clients, {nk8snodeslabel} must be greater '
             f'than {nhzmemberslabel}.')
if nhzmembers < minNodes:
    sys.exit(f"Must have at least {minNodes} nodes; {nhzmembers} set for "
             f"{nhzmemberslabel} in {myvarsf}.")

def tlsenabled() -> bool: return tlscoord

#
# GcpProjectId
#
gcpproject = ""
gcpaccount = ""
if target == "gcp":
    gcpproject = runCollect("gcloud config list --format "
                            "value(core.project)".split())
    gcpaccount = runCollect("gcloud config list --format "
                            "value(core.account)".split())

# Generate a unique octet for our subnet. Use that octet with the 'code' we
# generated above as part of a short name we can use to mark our resources
codelen = min(3, len(username))
nameprefix = username[:codelen]
s = username + zone
octet = int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 256
code = str(octet).zfill(3)
shortname = nameprefix + code
longname = username.replace('.', '-') + '-' + code

#
# Generate the main CIDR we will use in our cloud
#
def genmask(target, octet):
    assert octet < 256
    if target in ("aws", "az"):
        return f"10.{octet}.0.0/16"
    elif target == "gcp":
        # Get top four bits and combine with 2nd octet
        ipnum = 0xAC10 << 16 # 172.16.0.0
        ipnum |= octet << 12
        octets = []
        while ipnum > 0:
            octets.append(str(ipnum & 0xFF))
            ipnum >>= 8
        return ".".join(octets[::-1]) + "/20"

mySubnetCidr = genmask(target, octet)

#
# Determine which instance types we're using for this cloud target
#
instanceTypes: list[str] = []
smallInstanceType = ""
dbInstanceType = ""

if target == "aws":
    instanceTypes = myvars["AwsInstanceTypes"]
    smallInstanceType = myvars["AwsSmallInstanceType"]
elif target == "az":
    instanceTypes     = myvars["AzureVmTypes"]
    smallInstanceType = myvars["AzureSmallVmType"]
elif target == "gcp":
    instanceTypes     = myvars["GcpMachineTypes"]
    smallInstanceType = myvars["GcpSmallMachineType"]
else:
    sys.exit("Cloud target '{t}' specified for '{tl}' in '{m}' not one of "
             "{c}".format(t = target, tl = targetlabel, m = myvarsf,
                          c = ", ".join(clouds)))

assert len(instanceTypes) == 1

#
# Create some names for some cloud resources we'll need
#
clustname = shortname + "cl"
resourcegrp = shortname + "rg"
netwkname = shortname + 'net'

#
# Helm templates (yaml), releases, charts
templates = {}
releases = {}
charts = {}

operator_module = 'operator'
# no template for an operator!
releases[operator_module] = f'{operator_module}-{shortname}'
charts[operator_module] = 'hazelcast-platform-operator'

chaosmesh_module='chaos-mesh'
releases[chaosmesh_module] = f'{chaosmesh_module}-{shortname}'
charts[chaosmesh_module] = 'chaos-mesh'
chaosmeshoptions=(
        '--set chaosDaemon.runtime=containerd '
        '--set chaosDaemon.socketPath=/run/containerd/containerd.sock')

hz_crds = ['priclass', 'cluster', 'bbclient', 'bbclient_svc']
for crd in hz_crds:
    templates[crd] = f'{crd}_crd_v.yaml'

chaos_baselatency_crd = 'templates/chaos_baselatency.yaml'
chaos_splitdelay_crd = 'templates/chaos_splitdelay.yaml'
chaos_crds = [chaos_splitdelay_crd, chaos_baselatency_crd]

# Portfinder service

class Service:
    def __init__(self, name: str,
                 scheme: str,
                 lcl_port: int,
                 rmt_port: int):
        self.name = name
        self.scheme = scheme
        self.lcl_port = lcl_port
        self.rmt_port = rmt_port
        if scheme == 'https':
            self.tls = True
        else: # FIXME extend to other TLS-protected Hz connections
            self.tls = False

    def get_uri(self):
        return f'{self.scheme}://{self.name}.{domain}:{self.lcl_port}'

    def get_fqdn(self):
        return f'{self.name}.{domain}'

class Services:
    def __init__(self):
        svcs_list: set[Service] = {
                Service(srvnm_bbclient, "bbclient", 4000, 4000)
                }

        # Cluster services are more limited
        self.clust_svcs: dict[str, Service] = { i.name: i for i in svcs_list }

        # Total list of services includes the K8S API service
        self.svcs: dict[str, Service] = self.clust_svcs | {
                'apiserv': Service('apiserv', 'https', 2153, 443)
                }

    def get_all_svc_names(self):
        return self.svcs.keys()

    def get_clust_svc_names(self):
        return self.clust_svcs.keys()

    def get(self, name: str):
        return self.svcs[name]

    def get_clust_all(self):
        return iter(self.clust_svcs.values())

    def get_lcl_port(self, name: str) -> int:
        return self.svcs[name].lcl_port

    def get_rmt_port(self, name: str) -> int:
        return self.svcs[name].rmt_port

    def get_uri(self, name: str) -> str:
        return self.svcs[name].get_fqdn()

svcs = Services()

def random_string(length: int) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k = length))

def tmp_filename(prefix: str,
                 ext: str, 
                 my_tmp_dir: str = "",
                 random: bool = False) -> str:
    tmp_dir = tmpdir
    if my_tmp_dir:
        tmp_dir = my_tmp_dir
    fn = f'{tmp_dir}/{prefix}'
    if random:
        fn += '_' + random_string(4)
    fn += f'.{ext}'
    return fn

def convert_template_to_tmpname(template: str, my_tmp_dir: str = "") -> tuple[str, str, str]:
    assert os.path.basename(template) == template, \
            f"YAML template {template} should be in basename form (no path)"
    root, ext = os.path.splitext(template)
    if ext[0] == '.':
        ext = ext[1:] # get rid of leading period
    assert len(root) > 0 and len(ext) > 0
    # temporary file where we'll write the filled-in template
    return (tmp_filename(f'{root}_{shortname}', ext, my_tmp_dir=my_tmp_dir,
                         random=False), root, ext)

def appendToFile(filepath, contents) -> None:
    with open(filepath, "a+") as fh:
        fh.write(contents)

def replaceFile(filepath, contents) -> bool:
    newmd5 = hashlib.md5(contents.encode('utf-8')).hexdigest()
    root, ext = os.path.splitext(filepath)
    formats = {'.yaml': '#',
               '.tf': '#',
               '.zone': ';',
               '.hosts': '#'}

    if os.path.exists(filepath):
        if not os.path.isfile(filepath):
            sys.exit("{filepath} exists but isn't a file")
        # We have an old file by the same name. Check the extension, as we only
        # embed the md5 and version in file formats that take comments, and
        # .json files don't take comments.
        if ext in formats:
            with open(filepath) as fh:
                fl = fh.readline()
                if len(fl) > 0:
                    matchexpr = formats[ext] + r" md5 ([\da-f]{32})"
                    if match := re.match(matchexpr, fl):
                        if newmd5 == match.group(1):
                            # It's the same file. Don't bother writing it.
                            return False # didn't write
        # We have an old file, but the md5 doesn't match, indicating the new
        # one may be updated, so remove the old one.
        os.remove(filepath)

    # some of the files being written contain secrets in plaintext, so don't
    # allow them to be read by anyone but the user
    os.umask(0)
    flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL # we are writing new one
    try:
        with open(os.open(path=filepath, flags=flags, mode=0o600), 'w') as fh:
            if ext in formats:
                fh.write(formats[ext] + f' md5 {newmd5}\n')
            fh.write(contents)
    except IOError as e:
        print(f"Couldn't write file {filepath} due to {e}")
        raise
    return True # wrote new file

def removeOldVersions(similar: str) -> None:
    old = glob.glob(similar)
    for f in old:
        print(f"Removing old parameterised file {f}")
        os.remove(f)

def parameteriseTemplate(template: str, tmp_dir: str, varsDict: dict,
                         undefinedOk: set[str] = set()) -> tuple[bool, str]:
    yamltmp, root, ext = convert_template_to_tmpname(template, tmp_dir)

    # if we're writing a Terraform file, make sure to clean up older,
    # similar-looking Terraform files as these will cause Terraform to fail
    if ext == "tf":
        similar = f"{tmp_dir}/{root}*{ext}"
        removeOldVersions(similar)

    # render the template with the parameters, and capture result in memory
    try:
        file_loader = jinja2.FileSystemLoader(templatedir)
        env = jinja2.Environment(loader=file_loader, trim_blocks=True,
                                 lstrip_blocks=True,
                                 undefined=jinja2.DebugUndefined)
        t = env.get_template(template)
        output = t.render(varsDict)
        ast = env.parse(output)
        undefined = find_undeclared_variables(ast)
        if len(undefined - undefinedOk) > 0:
            raise jinja2.UndefinedError(f'Undefined vars in {template}: '
                                        f'{undefined}; undefinedOK'
                                        f'={undefinedOk}')
    except jinja2.TemplateNotFound as e:
        print(f"Couldn't read {template} from {templatedir} due to {e}")
        raise

    changed = replaceFile(yamltmp, output)
    return changed, yamltmp

class MissingTerraformOutput(Exception):
    pass

def get_output_vars() -> dict:
    x = json.loads(runCollect(f"{tf} output -json".split()))

    env = {k: v["value"] for k, v in x.items()}
    if not env:
        raise MissingTerraformOutput()

    if target == "aws":
        # Trim off everything on the AWS API server endpoint so that we're left
        # with just the hostname.
        ep = env.get('k8s_api_server')
        if not ep:
            raise MissingTerraformOutput()

        u = urlparse(ep)
        assert u.scheme is None or u.scheme == "https"
        assert u.port is None or u.port == 443
        env["k8s_api_server"] = u.hostname

    return env

class KubeContextError(Exception):
    pass

def updateKubeConfig() -> None:
    # Phase I: Write in the new kubectl config file as-is
    out.announce("Updating kube config file")
    if target == "aws":
        runStdout(f"aws eks update-kubeconfig --name {clustname}".split())
    elif target == "az":
        runStdout(f"az aks get-credentials --resource-group {resourcegrp} "
                  f"--name {clustname} --overwrite-existing".split())
    elif target == "gcp":
        runStdout(f"gcloud container clusters get-credentials {clustname} "
                  f"--region {zone} --internal-ip".split())

    # Phase II: Modify the config so that we use the proxy address and so that
    # we ignore the subject alternative names in the api-server certificate
    c = runCollect(f"{kube} config get-contexts "
                   "--no-headers".split()).splitlines()
    for line in c:
        columns = line.split()
        if columns[0] == "*":
            # get the cluster name
            cluster = columns[2]
            runStdout("kubectl config set clusters.{c}.server "
                      "https://{h}:{p}"
                      .format(c = cluster,
                              h = localhost,
                              p = svcs.get_lcl_port("apiserv")).split())
            runStdout(f"kubectl config set-cluster {cluster} "
                      "--insecure-skip-tls-verify=true".split())
            return
    raise KubeContextError(f"No active {kube} context within:\n{c}")

def get_my_pub_ip() -> ipaddress.IPv4Address:
    out.announce("Getting public IP address")
    try:
        i = runCollect("curl https://ipinfo.io/ip".split())
    except CalledProcessError:
        sys.exit("Unable to reach the internet. Are your DNS resolvers set "
                 "correctly?")

    try:
        myIp = ipaddress.IPv4Address(i)
        out.announceBox(f"Your visible IP address is {myIp}. Ingress to your "
                        "newly-created bastion server will be limited to this address "
                        "exclusively.")
        return myIp
    except ValueError:
        print(f"Unable to retrieve my public IP address; got {i}")
        raise

def get_ssh_pub_key() -> str:
    out.announce(f"Retrieving public ssh key {rsaPub}")
    try:
        with open(rsaPub) as rf:
            return rf.read()
    except IOError:
        sys.exit(f"Unable to read your public RSA key {rsaPub}")

def divideOrZero(x: int, y: int) -> float:
    assert x <= y, f"{x}, {y}"
    if y == 0:
        return 0.0
    else:
        return float(x) / float(y)

def waitUntilNodesReady(minNodes: int) -> float:
    ready_nodes, all_nodes = ready.get_nodes()
    numer = len(ready_nodes)
    denom = min(minNodes, len(all_nodes))
    return divideOrZero(numer, denom)

def waitUntilPodsReady(namespace: str, mincontainers: int = 0) -> float:
    ready_containers, all_containers = ready.summarize_containers(namespace)
    numer = len(ready_containers)
    denom = max(len(all_containers), mincontainers)
    return divideOrZero(numer, denom)

def waitUntilDeploymentsAvail(namespace: str, minreplicas: int = 0) -> float:
    numer = 0
    denom = 0
    namesp = f" --namespace {namespace}" if namespace else ""
    r = runTry(f"{kube}{namesp} get deployments -o json".split())
    if r.returncode == 0:
        deps = json.loads(r.stdout)['items']
        for dep in deps:
            reptotal = dep["spec"]["replicas"]
            repready = 0
            if "status" in dep:
                status = dep["status"]
                if "readyReplicas" in status:
                    repready = dep["status"]["readyReplicas"]
            assert repready <= reptotal
            numer += repready
            denom += reptotal
    if minreplicas:
        denom = min(minreplicas, denom)
    return divideOrZero(numer, denom)

def loadBalancerResponding(svc_name: str) -> bool:
    assert svc_name in svcs.get_clust_svc_names()

    # It is assumed this function will only be called once the ssh tunnels
    # have been established between the localhost and the bastion host
    try:
        # TODO: Need to check bbclient connection to test if it's responding
        return True
    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False
    except Exception as e:
        print(f'Unexpected exception {e}')
        return False

# Get a list of load balancers, in the form of a dictionary mapping service
# names to load balancer hostname or IP address. This function takes a list of
# service names, and returns any load balancers found. The list returned might
# not cover all the services presented, notably in the case when the load
# balancers aren't yet ready. The caller needs to be prepared for this
# possibility.
def getLoadBalancers(services: list, namespace: str) -> dict[str, str]:
    lbs: dict[str, str] = {}
    namesp = f" --namespace {namespace}" if namespace else ""
    for serv in services:
        r = runTry(f"{kube}{namesp} get svc -ojson {serv}".split())
        if r.returncode == 0:
            jout = json.loads(r.stdout)
            assert "items" not in jout
            s = jout

            # Metadata section
            meta = s["metadata"] # this should always be present
            assert meta["namespace"] == namespace # we only asked for this
            if "name" not in meta:
                continue
            name = meta["name"]
            assert name == serv, f"Unexpected service {name}"

            # Status section - now see if its IP is allocated yet
            if "status" not in s:
                continue
            status = s["status"]

            if "loadBalancer" not in status:
                continue
            lb = status["loadBalancer"]
            if "ingress" not in lb:
                continue
            ingress = lb["ingress"]
            assert len(ingress) == 1
            ingress0 = ingress[0]

            # Key could be either ip or hostname, both valid
            if "ip" in ingress0:
                lbs[name] = ingress0["ip"]
            elif "hostname" in ingress0:
                lbs[name] = ingress0["hostname"]
    return lbs

def waitUntilLoadBalancersUp(services: list, namespace: str,
                             checkConnectivity: bool = False) -> float:
    numer = 0
    denom = len(services)
    lbs = getLoadBalancers(services, namespace)
    for name in lbs.keys():
        if checkConnectivity and not loadBalancerResponding(name):
            continue

        # Found one service load balancer running
        numer += 1
    return divideOrZero(numer, denom)

def waitUntilApiServerResponding() -> float:
    # It is assumed this function will only be called once the ssh tunnels
    # have been established between the localhost and the bastion host
    url = ("https://{h}:{p}/"
           .format(h=localhost, p=svcs.get_lcl_port("apiserv")))
    try:
        r = requests.get(url, verify = False) # ignore certificate
        # Either forbidden (403), unauthorised (403) or 200 are acceptable
        if r.status_code in (401, 403, 200):
            return 1.0 # all done!
    except requests.exceptions.ConnectionError:
        pass
    return 0.0

# A class for recording ssh tunnels
class Tunnel:
    def __init__(self, shortname: str, bastionIp: ipaddress.IPv4Address,
                 lPort: int, rAddr: str, rPort: int):
        self.shortname = shortname
        self.bastion = bastionIp
        self.lport = lPort
        self.raddr = rAddr
        self.rport = rPort
        self.command = ("ssh -N -L{p}:{a}:{k} {bu}@{b}"
                        .format(p=lPort, a=rAddr, k=rPort, bu=bastionuser,
                                b=bastionIp))
        self.p: Optional[subprocess.Popen] = None

    def open(self):
        print(self.command)
        self.p = subprocess.Popen(self.command.split(),
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT)
        assert self.p is not None
        out.announce("Created tunnel " + str(self))

    def close(self):
        out.announce("Terminating tunnel " + str(self))
        assert self.p is not None
        self.p.terminate()
        self.p = None

    def __enter__(self):
        self.open()
        print(f'Tunnel OPENED: {self}')
        return self

    def __exit__(self, *_):
        self.close()
        print(f'Tunnel CLOSED: {self}')
        return False

    def __str__(self):
        tgtname = self.shortname
        if len(self.raddr) < 16:
            tgtname = "[{n}]{h}".format(n = self.shortname, h = self.raddr)
        s = '{l} -> {ra}:{rp}'.format(l=self.lport, ra=tgtname, rp=self.rport)
        if self.p:
            s += ' (PID {})'.format(self.p.pid)
        return s

# A class for logging pods
class PodLog:
    def __init__(self,
                 namespace: str,
                 name: str,
                 pod_selector: str,
                 container: str = ""):
        self.name = name
        self.pod_selector = pod_selector
        self.filename = tmp_filename(name, "log", random=True)
        self.fh = open(self.filename, "w+")
        self.thread: Optional[Thread] = None
        self.terminate = False
        container_switch = "--all-containers"
        if container:
            container_switch = f'--container={container}'
        self.command = (f'{kube} -n{namespace} logs -f --timestamps '
                        f'--tail=-1 {container_switch} --prefix '
                        f'--max-log-requests={maxloggedcns} '
                        f'-l{pod_selector}')
        self.thread = Thread(target=self.__log_forever_thread)
        self.thread.start()

    def __log_forever_thread(self):
        p = subprocess.Popen(self.command.split(),
                             stdout=self.fh,
                             stderr=subprocess.STDOUT)
        while True:
            subprocess_terminated = False
            return_code = 0
            try:
                return_code = p.wait(timeout=2) # wait for termination
                subprocess_terminated = True
            except subprocess.TimeoutExpired: # timeout completed
                pass

            if self.terminate: # someone wants us to stop
                if not subprocess_terminated:
                    p.terminate() # terminate child process
                break

            if subprocess_terminated:
                msg=('Previous log ended w/ RC={rc}. '
                     'Log restarting @{ts}: {me}'.format(
                         rc=return_code,
                         ts=str(datetime.now().time()),
                         me=str(self)))
                assert not self.fh.closed
                self.fh.write(msg + "\n") # write it to the log
                p = subprocess.Popen(self.command.split(),
                                     stdout=self.fh,
                                     stderr=subprocess.STDOUT)
                # Continue loop with new subprocess

    def __del__(self):
        self.terminate = True
        out.announce("Terminating log capture " + str(self))
        assert self.fh is not None
        self.fh.close()

    def __str__(self):
        return (f'{self.name} >> {self.filename}')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.terminate = True
        return False

# Input dictionary is the output variables from Terraform.
def setup_bastion_tunnel(bastion_ip: ipaddress.IPv4Address,
                         k8s_server_name: str) -> Tunnel:
    assert(bastion_ip)
    assert(k8s_server_name)
    # The new bastion server will have a new host key. Delete the old one we
    # have and grab the new one.
    out.announce(f"Replacing bastion host keys in {knownhosts}")
    try:
        runStdout(f'ssh-keygen -q -R {bastion_ip}'.split())
    except CalledProcessError:
        print("Unable to remove host key for {b} in {k}. Is file "
              "missing?".format(b = bastion_ip, k = knownhosts))
    cmd = f'ssh-keyscan -4 -p22 -H {bastion_ip}'
    print(cmd)
    cp = retryRun(cmd.split(), 10)
    hostkeys = cp.stdout.strip()
    print("Adding {n} host keys from bastion to {k}"
          .format(n=len(hostkeys.splitlines()), k=knownhosts))
    appendToFile(knownhosts, hostkeys)

    # Start up the tunnel to the Kubernetes API server
    tun = Tunnel("k8s-apiserver", bastion_ip, svcs.get_lcl_port("apiserv"),
                 k8s_server_name, svcs.get_rmt_port("apiserv"))
    tun.open()

    # Now that the tunnel is in place, update our kubecfg with the address to
    # the tunnel, keeping everything else in place
    updateKubeConfig()

    # Ensure that we can talk to the api server
    out.announce("Waiting for api server to respond")
    out.spinWait(waitUntilApiServerResponding)

    return tun

def terraform_start() -> None:
    # Get my public IP and SSH public key
    #
    my_pub_ip = get_my_pub_ip()
    my_ssh_pub_key = get_ssh_pub_key()

    # The terraform run. Perform an init, then an apply.
    tfenv = {"ClusterName":         clustname,
             "Domain":              domain,
             "InstanceTypes":       instanceTypes,
             "MaxPodsPerNode":      maxpodpnode,
             "MyCIDR":              mySubnetCidr,
             "MyPublicIP":          my_pub_ip,
             'NetwkName':           netwkname,
             "NodeCount":           nk8snodes,
             "SmallInstanceType":   smallInstanceType,
             "SshPublicKey":        my_ssh_pub_key,
             "Region":              region,
             "Target":              target,
             "UserName":            username,
             "ShortName":           shortname,
             "Zone":                zone}

    assert target in clouds

    if target == "az":
        tfenv["ResourceGroup"] = resourcegrp
    elif target == "gcp":
        tfenv["GcpProjectId"] = gcpproject
        tfenv["GcpAccount"] = gcpaccount

    parameteriseTemplate(tfvars, tfdir, tfenv)

    out.announce('running terraform init & apply')
    runStdout(f"{tf} init -upgrade -input=false".split())
    runStdout(f"{tf} apply -auto-approve -input=false".split())

def wait_until_k8s_is_ready() -> None:
    # Don't continue until all nodes are ready
    out.announce("Waiting for nodes to come online")
    out.spinWait(lambda: waitUntilNodesReady(nk8snodes))

    # Don't continue until all K8S system pods are ready
    out.announce("Waiting for K8S system pods to come online")
    out.spinWait(lambda: waitUntilPodsReady("kube-system"))

# Pods sometimes get stuck in Terminating phase after a helm upgrade.
# Kill these off immediately to save time and they will restart quickly.
def killAllTerminatingPods(namespace: str) -> None:
    lines = runCollect(f"{kube} -n {namespace} get pods "
                       "--no-headers".split()).splitlines()
    for line in lines:
        col = line.split()
        name = col[0]
        status = col[2]
        if status == "Terminating":
            r = runTry(f"{kube} -n {namespace} delete pod {name} "
                       "--grace-period=60".split())
            if r.returncode == 0:
                print(f"Cleaning up terminating pod {name}")

def kube_force_delete_all_pods_for_selector(namespace: str,
                                            selector: str) -> None:
    out.announce(f"Force-deleting all pods for {selector}")
    runStdout(f"{kube} -n {namespace} delete pod -l{selector} --force "
              "--grace-period=0".split())

# We run this command in 'delete' mode to get rid of the DNS record sets right
# before shutdown. Technically it shouldn't be needed for AWS or GCP, both of
# which have a 'force_destroy' option for the hosted zone that gets rid of
# record sets on destroy... but even these have many reported issues, so I
# don't want to rely on those to always work.
def set_dns_for_lbs(zid: str, # Zone ID
                    lbs: dict[str, str],
                    delete: bool = False) -> None:
    if not lbs:
        return
    assert(zid)

    action = "DELETE" if delete else "UPSERT"
    out.announce(f'{action} DNS entries for ' + ', '.join(lbs.keys()))
    ttl = 3600

    if target == 'aws':
        batch_aws: Dict[str, Any] = {
                'Comment': 'DNS CNAME records',
                'Changes': []
                }
    # for Azure & GCP, we will run commands as we go

    for svcname, host in lbs.items():
        assert svcname == 'bastion' or svcname in svcs.get_clust_svc_names()
        fqn = f'{svcname}.{domain}.'

        if target == 'aws':
            # AWS uses DNS names for LBs, not IP addresses, so we have to
            # create a CNAME record here, not an A record
            batch_aws['Changes'].append({
                'Action': action,
                'ResourceRecordSet': {
                    'Name': fqn,
                    'Type': 'CNAME',
                    'TTL': ttl,
                    'ResourceRecords': [{ 'Value': host }]}})
        elif target == 'az':
            # Azure uses IP addresses for LBs, so we use an A record. Azure
            # wants us to run a command for each update
            cmd = (f'az network private-dns record-set a delete '
                   f'-g {resourcegrp} -n {svcname} -z {zid} -y')
            runTry(cmd.split())
            if not delete:
                cmd = (f'az network private-dns record-set a create '
                       f'-g {resourcegrp} -n {svcname} -z {zid} --ttl {ttl}')
                cmd = (f'az network private-dns record-set a add-record '
                       f'-g {resourcegrp} -n {svcname} -z {zid} -a {host}')
                runIgnore(cmd.split())
        elif target == 'gcp':
            # GCP uses IP addresses for LBs, so we use an A record. GCP wants
            # us to run a command for each update.
            cmd = (f'gcloud dns record-sets delete {fqn} --zone={zid} '
                   '--type=A')
            runTry(cmd.split())
            if not delete:
                cmd = (f'gcloud dns record-sets create {fqn} --zone={zid} '
                       f'--type=A --rrdatas={host} --ttl={ttl}')
                runIgnore(cmd.split())

    if target == 'aws':
        batchfn = tmp_filename('crrs_batch_aws', 'json')
        replaceFile(batchfn, json.dumps(batch_aws))
        runIgnore(('aws route53 change-resource-record-sets --hosted-zone-id '
                   f'{zid} --change-batch file://{batchfn} '
                   '--no-cli-pager').split())
    # Nothing more to do for Azure or GCP

def wait_for_chaosmesh_pods() -> None:
    namespace = chaos_namespace
    cm_containers = ChaosMeshContainers()

    out.announce(f"Waiting for {namespace} pods to be ready")
    expectedContainers = cm_containers.numberOfContainers(nhzmembers, nhzclients)
    out.spinWait(lambda: waitUntilPodsReady(hz_namespace,
                                            expectedContainers))

    out.announce(f"Waiting for {namespace} deployments to be available")
    out.spinWait(lambda: waitUntilDeploymentsAvail(hz_namespace))

def wait_for_hazelcast_pods() -> None:
    hz_containers = HazelcastContainers()

    out.announce(f"Waiting for {hz_namespace} pods to be ready")
    expectedContainers = hz_containers.numberOfContainers(nhzmembers, nhzclients)
    out.spinWait(lambda: waitUntilPodsReady(hz_namespace, expectedContainers))

    out.announce(f"Waiting for {hz_namespace} deployments to be available")
    out.spinWait(lambda: waitUntilDeploymentsAvail(hz_namespace))

def wait_for_hazelcast_svcs(check_responding: bool = False) -> None:
    # now the load balancers need to be running with their IPs assigned
    verb = 'respond' if check_responding else 'launch'
    svcnames = list(svcs.get_clust_svc_names())
    svcnamesstr = ", ".join(svcnames)
    out.announce(f'Waiting for {hz_namespace} LBs to {verb}: {svcnamesstr}')
    out.spinWait(lambda: waitUntilLoadBalancersUp(svcnames, hz_namespace,
                                                  check_responding))

def create_tunnels_to_hz_svcs(bastion_addr: str) -> tuple[list[Tunnel],
                                                          dict[str, str]]:
    tuns: list[Tunnel] = []
    svcnames = list(svcs.get_clust_svc_names())

    #
    # Get the DNS name of the load balancers we've created
    #
    lbs = getLoadBalancers(svcnames, hz_namespace)

    # we should have a load balancer for every service we'll forward
    assert len(lbs) == len(svcnames)
    for svcname in svcnames:
        assert svcname in lbs
        tun = Tunnel(svcname, ipaddress.IPv4Address(bastion_addr),
                     svcs.get_lcl_port(svcname), lbs[svcname],
                     svcs.get_rmt_port(svcname))
        tuns.append(tun)

    return tuns, lbs

def convert_zulu_time_to_timestamp(datetimestr: str) -> float:
    # Google sometimes returns UTC dates with military/Zulu format; standardise
    # these here so we can parse them uniformly
    if datetimestr.endswith('Z'):
        datetimestr = datetimestr[:-1] + "+00:00"
    return datetime.timestamp(datetime.fromisoformat(datetimestr))

def k8s_secrets_list(namespace: str):
    installed_secrets = {}
    x = runCollect([kube, '-n', namespace, 'get', 'secrets',
                    '-o=jsonpath={range $.items[*].metadata}'
                    '{.name}{" "}{.creationTimestamp}{" "}{end}'])
    if x:
        s = x.split()
        z = zip(s[0::2], s[1::2])
        installed_secrets = {x: y for x, y in z}
    return installed_secrets

def k8s_secrets_create(namespace: str,
                       secrets_to_add: dict[str, dict[str, str]]) -> dict[str, str]:
    out.announce('Ensuring secrets are installed in K8S')
    env = {}
    installed_secrets = k8s_secrets_list(namespace)

    for secret_to_add_name, secret_to_add_content in secrets_to_add.items():
        # These are needed only for GCP
        if target != "gcp" and secret_to_add_name == "gcskey":
            continue

        # We always want to store the secret name, no matter what
        env[secret_to_add_name] = secret_to_add_name
        isgroup = secret_to_add_content.get('isgroup')

        # if this isn't a cert group, then record the base filename and fully
        # qualified filename to the environment dict
        file = ''
        file_arg = ''
        if not isgroup:
            env[secret_to_add_name + "bf"] = secret_to_add_content["bf"]
            env[secret_to_add_name + "f"] = secret_to_add_content["f"]
            file = secret_to_add_content['f']
            file_arg = file
            if (k := secret_to_add_content.get('k')):
                file_arg = f'{k}={file}'

        # if the secret with that name doesn't yet exist, create it; if there
        # is a newer version of the file, replace the secret with the newer one
        secret_ts_str = installed_secrets.get(secret_to_add_name)
        if secret_ts_str: # There is a secret already with that name
            secret_ts = convert_zulu_time_to_timestamp(secret_ts_str)
            file_ts = os.path.getmtime(file)

            # Secret already installed and file isn't newer -> NOOP
            if file_ts < secret_ts:
                continue

            print(f'Replacing secret "{secret_to_add_name}" '
                  f'with newer version of {file}')
            runIgnore(f'{kube} -n {namespace} delete secret '
                      f'{secret_to_add_name}'.split())
        else:
            print(f'Installing secret "{secret_to_add_name}" from {file}')

        # If this isn't a cert group, then install the secret normally. If
        # this is a cert group, and we are terminating TLS at an
        # ingress-based LB, then we need to install a secret that we'll use
        # in the helm chart with the LB.
        runIgnore(f'{kube} -n {namespace} create secret generic '
                  f'{secret_to_add_name} --from-file={file_arg}'.split())

    return env

def k8s_secrets_delete(namespace: str):
    installed_secrets = k8s_secrets_list(namespace)
    for secret in installed_secrets:
        runStdout(f'{kube} -n {namespace} delete secret {secret}'.split())

def k8s_pvc_delete(namespace: str):
    pvcs = json.loads(runCollect([kube, '-n', namespace, 'get',
                                  'pvc', '-ojson']))
    for pvc in pvcs['items']:
        pvcname = pvc['metadata']['name']
        runStdout(f'{kube} -n {namespace} delete pvc {pvcname} '
                  '--grace-period=0 --force'.split())

def k8s_restart(namespace: str, deployment: str):
    out.announce(f'Restarting and waiting for {deployment}...')
    runStdout([kube, "-n", namespace, "rollout", "restart", deployment])
    runStdout([kube, "rollout", "status", "--timeout=0", "--watch",
               deployment])
    print(f'Rolling restart of {deployment} complete')

def helmTry(namespace: str, cmd: str) -> subprocess.CompletedProcess:
    return runTry(['helm', '-n', namespace] + cmd.split())

def helmCmd(namespace: str, cmd: str) -> None:
    runStdout(['helm', '-n', namespace] + cmd.split())

def helmGet(namespace: str, cmd: str) -> str:
    return runCollect(['helm', '-n', namespace] + cmd.split())

def helmIgnore(namespace: str, cmd: str) -> None:
    runIgnore(['helm', '-n', namespace] + cmd.split())

def helm_set_up_repo(namespace: str,
                     helm_repo_name: str,
                     helm_repo_location: str) -> None:
    if (r := helmTry(namespace, "version")).returncode != 0:
        sys.exit("Unable to run helm. Is it installed? Failing out.")

    # There is a bug in helm repo list, wherein it inconsistently returns
    # nonzero error codes when there are no repos installed. So just try to
    # fast-path the common case where the repo is already installed, and
    # otherwise try to install.
    if (r := helmTry(namespace, "repo list -o=json")).returncode == 0:
        repos = [x["name"] for x in json.loads(r.stdout)]
        if helm_repo_name in repos:
            # Unfortunately, helm repo update returns a 0 error code even when
            # it fails. So we actually have to collect the output and look to
            # see if it failed. :-( If it fails, then just remove the repo and
            # re-install it.
            out.announce(f'Updating helm repo {helm_repo_name}')
            output = helmGet(namespace, "repo update --fail-on-repo-update-fail")
            if "Update Complete. ⎈Happy Helming!⎈" in output:
                print("Upgrade of repo succeeded")
                return

            out.announce(f'Update of repo failed. Removing '
                         f'repo {helm_repo_name}')
            helmCmd(namespace, f'repo remove {helm_repo_name}')

    crepouser = ''
    crepopass = ''
    helmCmd(namespace, f'repo add {crepouser} {crepopass} '
            f'{helm_repo_name} {helm_repo_location}')

def helmGetNamespaces() -> list:
    n = []
    try:
        nsl = json.loads(runCollect(f"{kube} get namespaces "
                                    "--output=json".split()))["items"]
        n = [x["metadata"]["name"] for x in nsl]
    except CalledProcessError:
        print("No namespaces found.")

    return n

def k8s_create_namespace(namespace: str) -> None:
    if namespace not in helmGetNamespaces():
        runStdout(f'{kube} create namespace {namespace}'.split())

def k8s_set_context_namespace(namespace: str) -> None:
    assert namespace in helmGetNamespaces()
    runStdout(f'{kube} config set-context --namespace={namespace} '
              '--current'.split())

def k8s_delete_namespace(namespace: str) -> None:
    if namespace in helmGetNamespaces():
        out.announce(f"Deleting namespace {namespace}")
        runStdout(f'{kube} delete --grace-period=60 '
                  f'namespace {namespace}'.split())
    runStdout(f"{kube} config set-context --namespace=default "
              "--current".split())

def helmGetReleases(namespace: str) -> dict:
    rls = {}
    try:
        rlsj = json.loads(helmGet(namespace, "list -ojson"))
        rls = { r["name"]: r["chart"] for r in rlsj }
    except CalledProcessError:
        print("No helm releases found.")
    return rls

def helmWhichChartInstalled(namespace: str, module: str) -> Optional[str]:
    chart = None
    release = releases[module] # Get release name for module name
    installed = helmGetReleases(namespace)
    if release in installed:
        chart = installed[release] # Get chart for release
    return chart

def helm_install_release(namespace: str,
                         reponame: str,
                         module: str,
                         version: str,
                         options: str = "") -> None:
    chart = helmWhichChartInstalled(namespace, module)
    newchart = charts[module] + "-" + version # which one to install?

    if chart is None: # Nothing installed yet, so we need to install
        out.announce("Installing {ns}/{r} v{v}"
                     .format(ns=namespace, r=releases[module], v=version))
        helmIgnore(namespace, 'install {r} {repo}/{c} --version {v} {o}'
                   .format(r=releases[module], repo=reponame, c=charts[module],
                           v=version, o=options))
    # If either the chart values file changed, or we need to update to a
    # different version of the chart, then we have to upgrade
    elif chart != newchart:
        astr = "Upgrading {ns}/{r} v{v}".format(ns=namespace,
                                                r=releases[module],
                                                v=version)

    if chart != newchart:
        astr += ": {oc} -> {nc}".format(oc = chart, nc = newchart)
        out.announce(astr)
        helmIgnore(namespace, 'upgrade {r} {repo}/{c} --version {v} {o}'
                   .format(r=releases[module], repo=reponame, c=charts[module],
                           v=version, o=options))
    else:
        print(f'{namespace}/{chart} values unchanged ➼ avoiding helm upgrade')

def kube_crd_apply(crd: str, namespace: str) -> None:
    out.announce(f'Applying CRD "{crd}"')
    runStdout(f'{kube} -n {namespace} apply -f {crd}'.split())

def kube_crd_apply_templated(crd: str, namespace: str, env: dict = {}) -> None:
    # Ignore changes, apply every time
    _, yamltmp = parameteriseTemplate(templates[crd], tmpdir, env)
    kube_crd_apply(yamltmp, namespace)

def k8s_crd_delete(filename: str, namespace: str):
    if bbio.readableFile(filename):
        out.announce(f'Deleting CRD "{filename}"')
        runTry(f'{kube} -n {namespace} delete --grace-period=60 '
               f'--ignore-not-found=true -f {filename}'.split())

def k8s_crd_delete_templated(crd: str, namespace: str, env) -> None:
    # Generate filename of tmp file where CRD lives
    yamltmp, _, _ = convert_template_to_tmpname(templates[crd])
    k8s_crd_delete(yamltmp, namespace)

def helmUninstallRelease(namespace: str, release: str) -> None:
    helmCmd(namespace, f"uninstall {release}")

def delete_all_services(namespace: str) -> bool:
    # Explicitly deleting services gets rid of load balancers, which eliminates
    # a race condition that Terraform is susceptible to, where the ELBs created
    # by the load balancers endure while the cluster is destroyed, stranding
    # the ENIs and preventing the deletion of the associated subnets
    # https://github.com/kubernetes/kubernetes/issues/93390
    out.announce(f"Deleting all k8s services for namespace {namespace}")
    lbs_before: dict[str, str] = getLoadBalancers(svcs.get_clust_svc_names(),
                                                  namespace)

    # Summarize which LBs were there before attempt to kill services
    if len(lbs_before) == 0:
        print("No LBs running before deleting all services.")
    else:
        print("Load balancers before attempt "
              "to delete services: " + ", ".join(lbs_before.keys()))

    # Destroy all services!
    runStdout(f'{kube} -n {namespace} delete '
              '--grace-period=60 svc --all'.split())
    lbs_after = getLoadBalancers(svcs.get_clust_svc_names(),
                                 namespace)

    # Indicate if any LBs remain after killing services
    if len(lbs_after) != 0:
        print("# WARN Load balancers running after service delete! " +
              str(lbs_after))
        print("# WARN This may cause dependency problems later!")
        return False

    print("No load balancers running after service delete.")
    return True

def helm_uninstall_releases_and_kill_pods(namespace: str):
    for release, chart in helmGetReleases(namespace).items():
        try:
            out.announce(f"Uninstalling {namespace}/{release}")
            helmUninstallRelease(namespace, release)
        except CalledProcessError as e:
            print(f"Unable to uninstall release {release}: {e}")
    killAllTerminatingPods(namespace)

def start_await_hz_and_chaos_pods_srvcs(env: dict[str, str],
                                        secrets: dict[str, dict[str, str]]) -> None:
    # Do this first so all resources install into the namespace
    with Timer(f'set up {hz_namespace} namespace objects in K8S'):
        #
        # Hazelcast namespace objects
        #
        k8s_create_namespace(hz_namespace)
        k8s_set_context_namespace(hz_namespace) # default namespace

        env |= {
                appversionlabel: appversion,
                'HzClientCount': nhzclients,
                'HzMemberCount': nhzmembers,
                'SrvNmCluster': srvnm_cluster
                }

        env |= k8s_secrets_create(hz_namespace, secrets)

        # Set up the Helm repo if not already done
        helm_set_up_repo(hz_namespace, hz_helm_repo_name,
                         hz_helm_repo_location)

        helm_install_release(hz_namespace, hz_helm_repo_name, operator_module,
                             oprchartversion)
        for crd in hz_crds:
            kube_crd_apply_templated(crd, hz_namespace, env)

        kube_force_delete_all_pods_for_selector(hz_namespace, devpodsel)
        kube_force_delete_all_pods_for_selector(hz_namespace, bbclientpodsel)

        # Speed up the deployment of the updated pods by killing the old ones
        killAllTerminatingPods(hz_namespace)
        wait_for_hazelcast_pods()
        wait_for_hazelcast_svcs()

    if ns.test:
        with Timer(f'set up {chaos_namespace} namespace objects in K8S'):
            #
            # Chaos-Mesh namespace objects
            #
            k8s_create_namespace(chaos_namespace)

            # Set up the Chaos Mesh repo if not already done
            helm_set_up_repo(chaos_namespace, chaos_helm_repo_name,
                             chaos_helm_repo_location)

            helm_install_release(chaos_namespace, chaos_helm_repo_name,
                                 chaosmesh_module, chaoschartversion,
                                 chaosmeshoptions)

            # TODO: There is a bug in chaos-mesh in the auth module, that prevents
            # chaos-mesh from working across namespaces. This is the workaround:
            runIgnore(f'{kube} -n {chaos_namespace} delete '
                      '--ignore-not-found=true '
                      'validatingwebhookconfigurations.admissionregistration.k8s.io '
                      'chaos-mesh-validation-auth'.split())

            # Speed up the deployment of the updated pods by killing the old ones
            killAllTerminatingPods(chaos_namespace)

            wait_for_chaosmesh_pods()

            # Get rid of any existing split-delay workflow, then apply the
            # chaos-mesh workflow for some (small) increased latency between
            # members. Note that this must be applied in the Hazelcast namespace,
            # not in the chaos-mesh namespace.
            k8s_crd_delete(chaos_splitdelay_crd, hz_namespace)
            kube_crd_apply(chaos_baselatency_crd, hz_namespace)

def svcStop(onlyEmptyNodes: bool = False) -> None:
    # Re-establish the tunnel with the bastion to allow our commands to flow
    # through to the K8S cluster.
    out.announce("Re-establishing bastion tunnel")
    lbs_were_cleaned = True

    try:
        env = get_output_vars()
        zone_id = env['zone_id']
        bastion_ip = env['bastion_address']
        k8s_server_name = env['k8s_api_server']

        # We need the bastion tunnel up in order to fetch the LBs
        with setup_bastion_tunnel(bastion_ip, k8s_server_name):
            # NOTE: DNS *must* be removed since Terraform will complain about any
            # records it didn't create at the time the zone is destroyed.
            lbs = getLoadBalancers(svcs.get_clust_svc_names(), hz_namespace)
            try:
                set_dns_for_lbs(zone_id, lbs, delete=True)
            except CalledProcessError:
                print('Unable to delete DNS record sets (do they exist?)')

            # tunnel established. Now delete things in reverse order to how
            # they were created.

            if ns.test:
                with Timer('teardown of chaos-mesh K8S resources'):
                    # Delete all the CRDs applied. Note that the chaos-mesh
                    # workflow is installed in the Hazelcast namespace, not the
                    # chaos-mesh namespace.
                    for crd in chaos_crds:
                        k8s_crd_delete(crd, hz_namespace)
                    helm_uninstall_releases_and_kill_pods(chaos_namespace)
                    if ns.test:
                        lbs_were_cleaned = (lbs_were_cleaned and
                                            delete_all_services(chaos_namespace))
                    k8s_secrets_delete(chaos_namespace)
                    k8s_pvc_delete(chaos_namespace)
                    k8s_delete_namespace(chaos_namespace)

            with Timer('teardown of K8S resources'):
                for crd in hz_crds:
                    k8s_crd_delete_templated(crd, hz_namespace, env)

                helm_uninstall_releases_and_kill_pods(hz_namespace)

                # Make sure to get rid of all services, in case they weren't
                # already removed. We need to make sure we don't leak LBs.
                lbs_were_cleaned = (lbs_were_cleaned and
                                    delete_all_services(hz_namespace))

                k8s_secrets_delete(hz_namespace)
                k8s_pvc_delete(hz_namespace)
                k8s_delete_namespace(hz_namespace)
    except (MissingTerraformOutput):
        out.announce('Terraform objects partly or fully destroyed')

    if onlyEmptyNodes:
        return

    if not lbs_were_cleaned:
        out.announceBox(textwrap.dedent("""\
                I was unable to clear away load balancers. I will try to destroy
                your terraform, but you might have trouble on the destroy with
                leaked LBs."""))

    out.announce(f"Ensuring cluster {clustname} is deleted")
    with Timer('stopping cluster'):
        runStdout(f"{tf} destroy -auto-approve".split())

def getCloudSummary() -> List[str]:
    if target == "aws":
        cloud = "Amazon Web Services"
    elif target == "az":
        cloud = "Microsoft Azure"
    else:
        cloud = "Google Cloud Services"

    return [f"Cloud: {cloud}",
            f"Region: {region}",
            # FIXME this should show the instance type actually selected!
            f"Cluster: {nk8snodes} × {instanceTypes[0]}"]

def load_secrets_from_file() -> dict[str, dict[str, str]]:
    secrets: dict[str, dict[str, str]] = {}
    try:
        with open(secretsf) as fh:
            s = yaml.load(fh, Loader = yaml.FullLoader)
    except IOError:
        sys.exit(f"Couldn't read secrets file {secretsf}")

    groups: dict[str, dict[str, Any]] = {}

    for name, values in s.items():
        base = values["bf"]
        if "dir" in values:
            base = values["dir"] + "/" + base
        filename = bbio.where(base)

        # If the secret is not generated later by this program, then it is
        # a pre-made secret, and it must already be on disk and readable.
        if ("generated" not in values or not values["generated"]) \
                and not bbio.readableFile(filename):
                    sys.exit(f"Can't find a readable file at {filename} "
                             f"for secret {name}")

        # Certificate groups should be treated specially, and we should add
        # these to the set as a single object. Store them away here and return
        # back after this loop to record them as groups.
        if "group" in values:
            groupname = values["group"]
            grouptype = values["type"]
            if groupname in groups:
                groups[groupname][grouptype] = filename
            else:
                groups[groupname] = { "isgroup": True, grouptype: filename }
            continue

        values["f"] = filename
        secrets[name] = values

    for groupname, values in groups.items():
        # at least "cert" and "key" have to be members of the group; a "chain"
        # value may also be present optionally
        assert "cert" in values and "key" in values, \
                f"cert and key not found together for {groupname}"
        # if there is a chain, and we have enabled TLS to the coordinator, then
        # verify the certificate and chain
        if "chain" in values and tlsenabled():
            # openssl always returns 0 as the return code, so we have to
            # actually parse the output to see if the certificate is valid
            try:
                output = runCollect("openssl verify -untrusted {ch} {c}"
                                    .format(ch=values["chain"],
                                            c=values["cert"]).split()).splitlines()
                if output[-1] == values['cert'] + ': OK':
                    print('Verified certificate ' + values["cert"])
            except CalledProcessError:
                print("Unable to verify cert {c} & chain {ch}"
                      .format(c=values["cert"], ch=values["chain"]))
                sys.exit(-1)
        secrets[groupname] = values

    return secrets

def announceSummary() -> None:
    out.announceLoud(getCloudSummary())

def checkRSAKey() -> None:
    if bbio.readableFile(rsa) and bbio.readableFile(rsaPub):
        return

    print(f"You do not have readable {rsa} and {rsaPub} files.")
    yn = input("Would you like me to generate them? [y/N] -> ")
    if yn.lower() in ("y", "yes"):
        rc = runShell(f"ssh-keygen -q -t rsa -N '' -f {rsa} <<<y")
        if rc == 0:
            print(f"Generated {rsa} file.")
            return
        else:
            print(f"Unable to write {rsa}. Try yourself?")
    sys.exit(f"Script cannot continue without {rsa} file.")

def checkEtcHosts() -> None:
    out.announce(f'Ensuring needed mapping entries are in {hostsf}')
    tmpfile = tmp_filename('etc', 'hosts')

    # Start by trying to see if the entries are already in the hosts file, in
    # the form we want. If they are, we don't need to create them.
    hosts_checklist = set(svcs.get_all_svc_names())
    hosts_found = set()
    modified = False

    with open(hostsf) as rfh, open(tmpfile, 'w') as wfh:
        r = re.compile(r"^\s*"
                       r"([\.:\d]*)"
                       r"\s+"
                       r"((?=.{1,255}$)[A-Za-z0-9\-]{1,63})"
                       r"((\.[A-Za-z0-9\-]{1,63})*)"
                       r"\.?"
                       r"(?<!-)$")

        for line in rfh:
            # skip commented lines
            rexp = r.match(line)

            if rexp:
                ip, hostname, fqdomain = rexp.group(1,2,3)

                # This is some kind of mapping entry. If it maps to localhost,
                # then this might be one of the service mapping entries we're
                # looking for.
                if ip == localhostip and fqdomain and fqdomain == f'.{domain}':
                    if hostname in hosts_checklist:
                        # Success! We have found one of the needed hosts.
                        # Write the new line to our new temp file, and remove
                        # the found host from our checklist.
                        hosts_checklist.remove(hostname)
                        hosts_found.add(hostname)
                    else:
                        # This means we found our special fqdomain in the line,
                        # but it doesn't include one of our known services.
                        print(f'Dropping entry: unexpected host {hostname}')
                        modified = True
                        continue

            # Write the line through to the output file
            wfh.write(line)

        # Write all the hosts that we didn't find as new lines
        for host in hosts_checklist:
            modified = True
            wfh.write(f'{localhostip}\t{host}.{domain}\n')

    if hosts_found:
        print(f'Found valid {hostsf} entries for ' + ', '.join(hosts_found))

    if modified:
        print('You need to have DNS entries for ' + ', '.join(hosts_checklist)
              + f' in {hostsf}.')
        print(f'The following changes to your {hostsf} are suggested:')
        try:
            # diff returns 0 for no differences, 1 for differences, or > 1 if
            # there was some kind of error
            runStdout(f'diff --unified {hostsf} {tmpfile}'.split())
            # We shouldn't get here, because it would imply diff returned
            # exitcode==0, which means that the new /etc/hosts file didn't have
            # any changes... which it should.
            sys.exit('Should have found differences but did not')
        except CalledProcessError as cpe:
            # Shouldn't be here unless returncode was nonzero
            assert cpe.returncode > 0
            # We got a geniune diff error
            if cpe.returncode > 1:
                raise
            elif cpe.returncode == 1:
                # This is the *expected* path, since we only get to this point
                # if there were modifications to the /etc/hosts file, and diff
                # returns exitcode==1 if there were changes
                pass

        cmd = f'cat {tmpfile} | sudo tee {hostsf}'
        yn = input(f'Implement these changes to your {hostsf}, '
                   'using sudo? [y/N] -> ')
        if yn.lower() in ('y', 'yes'):
            runShell(cmd)
            print(f'{hostsf} successfully updated.')
        else:
            sys.exit('Cannot continue without these changes.')

def cleanOldTunnels() -> None:
    # Check to see if anything looks suspiciously like an old ssh tunnel, and
    # see if the user is happy to kill them.
    out.announce('Looking for old tunnels to clean')
    srchexp = f'ssh -N -L.+:.+:.+ {bastionuser}@'
    r = re.compile(srchexp)
    def get_tunnel_procs():
        nonlocal r
        tunnels = []
        for proc in psutil.process_iter(attrs=['pid', 'cmdline']):
            if not proc.info['cmdline']:
                continue
            if r.match(" ".join(proc.info['cmdline'])):
                tunnels.append(proc)
        return tunnels

    while True:
        procs = get_tunnel_procs()
        if not procs:
            break

        for proc in procs:
            print(str(proc.info['pid']) + ' - ' +
                  " ".join(proc.info['cmdline']))

        yn = input('These look like old tunnels. Kill them? [Y/n] -> ')
        if not yn or yn.lower()[0] == 'y':
            for proc in procs:
                proc.terminate()
        else:
            break

def spinWaitCGTest():
    waits = []
    for i in range(random.randrange(5, 21)):
        waits.append(random.randrange(1, 11))
    out.announceBox(f'Waits are {waits}')
    cg = CommandGroup()
    for w in waits:
        def make_cb(w: int) -> Callable[[], None]:
            def sleep_x() -> None:
                time.sleep(float(w))
            return sleep_x
        cg.add_command(make_cb(w), w)
    cg.run_commands()
    out.spinWait(cg.ratio_done)
    cg.wait_until_done()

def check_creds() -> None:
    awsdir    = os.path.expanduser("~/.aws")
    awsconfig = os.path.expanduser("~/.aws/config")

    if target == "aws":
        badAws = False
        if not bbio.writeableDir(awsdir):
            badAws = True
            err = f"Directory {awsdir} doesn't exist or has bad permissions."
        elif not bbio.readableFile(awsconfig):
            badAws = True
            err = f"File {awsconfig} doesn't exist or isn't readable."
        if badAws:
            print(err)
            sys.exit("Have you run aws configure?")
        out.announce('Validating AWS SSO token')
        try:
            runIgnore('aws sts get-caller-identity --no-cli-pager'.split())
            print('Your AWS SSO token is valid')
        except CalledProcessError:
            yn = input("Your AWS SSO token is stale. Refresh it now? [y/N] -> ")
            if yn.lower() in ("y", "yes"):
                try:
                    runStdout('aws sso login'.split())
                    return
                except CalledProcessError:
                    pass
            sys.exit('Cannot continue with stale AWS SSO token')
    elif target == "az":
        azuredir = os.path.expanduser("~/.azure")
        if not bbio.writeableDir(azuredir):
            print(f"Directory {azuredir} doesn't exist or isn't readable.")
            sys.exit("Have you run az login and az configure?")
    elif target == "gcp":
        gcpdir = os.path.expanduser("~/.config/gcloud")
        if not bbio.writeableDir(gcpdir):
            print("Directory {gcpdir} doesn't exist or isn't readable.")
            sys.exit("Have you run gcloud init?")

def get_hz_cluster_podnames(ss_selector: str) -> list[str]:
    return runCollect([kube, '-n', hz_namespace, 'get', 'pods',
                       f'-l{ss_selector}',
                       '-ojsonpath={.items[*].metadata.name}']).split()

def log_hz_cluster_member(ss_selector: str, podname: str) -> PodLog:
    selectors: list[str] = [ss_selector]
    selectors.append(f'statefulset.kubernetes.io/pod-name={podname}')
    return PodLog(hz_namespace,
                  podname,
                  ",".join(selectors),
                  container='hazelcast')

def bbclient_communicate() -> str:
    dev0_pod_ip = runCollect([kube, 'get', 'pods',
                              '-o=jsonpath={.items[?(@.metadata.name=="' +
                              srvnm_cluster + "-0" +
                              '")].status.podIP}'])
    def send_and_check_resp(command: str,
                            can_retry: bool,
                            verbose: bool = True) -> tuple[bool, str]:
        rc_is_ok = False
        return_val: str = ""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((svcs.get_uri(srvnm_bbclient),
                       svcs.get_lcl_port(srvnm_bbclient)))

            # Client always initiates send...
            f = s.makefile("rw")
            if verbose:
                print(f'Sending: {command}')
            f.write(command + "\n")
            f.flush()
            # ...then awaits the response
            line = f.readline()

            if line.startswith("BB 200 OK"):
                rc_is_ok = True
                slices = line.split(":", 1)
                if len(slices) == 2:
                    return_val = slices[1].strip()
                    print(f'Got back: {return_val}')
            elif line.startswith("BB 408 TIMEOUT") and can_retry:
                rc_is_ok = False
            else:
                sys.exit("Got unexpected result: " + line)
            s.close()

        return rc_is_ok, return_val

    stages: list[dict] = [{'command': 'HELO', 'can_retry': False},
                          {'command': f'ADDR {dev0_pod_ip}', 'can_retry': False},
                          {'command': 'TEST', 'can_retry': True},
                          {'command': 'STRT', 'can_retry': False},
                          {'command': 'WTST', 'can_retry': True},
                          {'command': 'STOP', 'can_retry': False}]

    return_val: str = ""

    for stage in stages:
        verbose = True
        while True:
            if stage['command'] == 'STRT':
                kube_crd_apply(chaos_splitdelay_crd, hz_namespace)
            elif stage['command'] == 'STOP':
                k8s_crd_delete(chaos_splitdelay_crd, hz_namespace)

            rc_is_ok, rval = send_and_check_resp(stage['command'],
                                                 stage['can_retry'],
                                                 verbose)

            if rc_is_ok:
                print('SUCCESS')
                if rval:
                    print(f'RETURN VALUE: {rval}')
                    return_val = rval
                break
            else: # retry
                if verbose:
                    print("Waiting on server...", end='', flush=True)
                    verbose = False
                else:
                    print('.', end='', flush=True)
                time.sleep(5)
                continue

    return return_val

#def main_test() -> None:
#    test_output_fn = tmp_filename('test_output', 'out', random=True)
#    print(f'Writing test output to {test_output_fn}')
#    with open(test_output_fn, 'w') as test_output_fh:
#        for i in range(0, 10):
#            if not ns.skip_cluster_start:
#                with Timer('set up infrastructure in Terraform'):
#                    terraform_start()
#            env = get_output_vars()
#            bastion_addr = env['bastion_address']
#            k8s_api_addr = env['k8s_api_server']
#            with setup_bastion_tunnel(bastion_addr,
#                                      k8s_api_addr) as bastion_tun:
#            start_await_hz_and_chaos_pods_srvcs(secrets, ns.skip_cluster_start)
#
#            # Wait for pods & LBs to become ready
#            # Set up port forward tunnels for LBs
#            hz_tuns, hz_srv_lbs = create_tunnels_to_hz_svcs(bastion_addr)
#            wait_for_hazelcast_svcs(check_responding = True)
#
#            # Set up DNS to new Hazelcast services
#            set_dns_for_lbs(env['zone_id'], hz_srv_lbs)
#
#            with ExitStack() as stack:
#                for tun in hz_tuns:
#                    stack.enter_context(tun)
#                podnames = get_hz_cluster_podnames(ss_selector)
#                logs = [stack.enter_context(log_hz_cluster_member(ss_selector,
#                                                                  podname))
#                        for podname in podnames]
#                for log in logs:
#                    out.announce("Log started for " + str(log))
#
#                out.announceBox(f'Your {rsaPub} public key has been installed into '
#                                f'the bastion server, so you can ssh there now '
#                                f'(user "{bastionuser}").')
#                y = cloud_summary + (['Service is started on:'] +
#                                     [f'[{s.name}] {s.get_uri()}' for s in svcs.get_clust_all()])
#                out.announceLoud(y)
#                return_val = bbclient_communicate()
#                if return_val:
#                    print(f'Writing return_val={return_val} '
#                          f'to {test_output_fn}')
#                    test_output_fh.write(return_val + '\n')
#                    test_output_fh.flush()
#                #input("Press return key to quit and terminate tunnels!")
#                #out.announceLoud(["Terminating all tunnels and logging"])
#            for tun in tuns:
#                tun.close()

def main() -> None:
    if ns.progmeter_test:
        spinWaitCGTest()
        sys.exit(0)

    out.announce("Verifying environment")
    secrets = load_secrets_from_file()
    announceSummary()
    check_creds()
    checkRSAKey()
    checkEtcHosts()
    cleanOldTunnels()
    if target == "gcp":
        out.announce(f"GCP project is {gcpproject}")
    print(f"Your CIDR is {mySubnetCidr}")

    cloud_summary = getCloudSummary()

    if ns.command not in ('start', 'stop'):
        sys.exit(f'Invalid command {ns.command}')

    if ns.command == 'stop':
        svcStop(ns.empty_nodes)
        y = cloud_summary + ['Service is stopped']
        out.announceLoud(y)
        return

    # ns.command == 'start'

    if not ns.skip_cluster_start:
        with Timer('set up infrastructure in Terraform'):
            terraform_start()

    env = get_output_vars()
    bastion_addr = env['bastion_address']
    k8s_api_addr = env['k8s_api_server']
    with setup_bastion_tunnel(bastion_addr,
                              k8s_api_addr):
        start_await_hz_and_chaos_pods_srvcs(env, secrets)

        # Create--but do not start--port-forward tuns for Hazelcast svc LBs
        hz_tuns, hz_srv_lbs = create_tunnels_to_hz_svcs(bastion_addr)

        # Wait until Hz svc LBs start responding
        wait_for_hazelcast_svcs(check_responding = True)

        # Set up cloud DNS to new Hazelcast services
        set_dns_for_lbs(env['zone_id'], hz_srv_lbs)

        with ExitStack() as stack:
            # Now actually open the tunnels using a resource manager
            for tun in hz_tuns:
                stack.enter_context(tun)

            out.announceBox(f'Your {rsaPub} public key has been installed into '
                            f'the bastion server {bastion_addr}, so you can '
                            f'ssh there now (user "{bastionuser}").')
            y = cloud_summary + (['Service is started on:'] +
                                 [f'[{s.name}] {s.get_uri()}'
                                  for s in svcs.get_clust_all()])
            out.announceLoud(y)
            input("Press return key to quit and terminate tunnels!")
            out.announceLoud(["Terminating all tunnels and logging"])

main()
