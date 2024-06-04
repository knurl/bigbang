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
from datetime import datetime

from subprocess import CalledProcessError
from typing import List, Callable, Optional, Any, Dict
from urllib.parse import urlparse
import jinja2
from jinja2.meta import find_undeclared_variables

import logging

from urllib3 import disable_warnings # type: ignore

# local imports
import out
import bbio
import ready # local imports
from cmdgrp import CommandGroup
from capcalc import numberOfReplicas, numberOfContainers
from run import runShell, runTry, runStdout, runCollect, retryRun, runIgnore
from timer import Timer

# Suppress info-level messages from the requests library
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# Do this just to get rid of the warning when we try to read from the
# api server, and the certificate isn't trusted
disable_warnings()

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
dbports       = { "mysql": 3306, "postgres": 5432 }
localhost     = "localhost"
localhostip   = "127.0.0.1"
domain        = "hazelcast.net" # cannot terminate with .; Azure will reject
srvnm_manctr  = 'manctr'
srvnm_cluster = 'cluster'
bastionuser   = 'ubuntu'

# K8S / Helm
namespace   = "hazelcast"
kube        = "kubectl"
kubens      = f"{kube} -n {namespace}"
helmns      = f"-n {namespace}"
minNodes    = 3 # See getMinNodeResources(); allows rolling upgrades
maxpodpnode = 32

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
               help="Unload k8s cluster only. Used with stop or restart.")
p.add_argument('-s', '--summarise-ssh-tunnels', action="store_true",
               help="Summarise the ssh tunnels on exit.")
p.add_argument('-t', '--target', action="store",
               help="Force cloud target to specified value.")
p.add_argument('-z', '--zone', action="store",
               help="Force zone/region to specified value.")
p.add_argument('command',
               choices = ['start', 'stop', 'restart'],
               help="""Start/stop/restart the demo environment.""")
p.add_argument('-P', '--progmeter-test', action="store_true",
               help=argparse.SUPPRESS)

ns = p.parse_args()

# Options which can only be used with start (or restart)
if ns.command not in ("start", "restart"):
    v = vars(ns)
    for switch in {"dont_load", "skip_cluster_start", "drop_tables"}:
        if switch in v and v[switch]:
            p.error(f"{switch} is only used with start (or restart)")

# Options which can only be used with stop (or restart)
if ns.command not in ("stop", "restart") and ns.empty_nodes:
    p.error("empty_nodes is only used with stop or restart")

#
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd config file,
# very small, called ./helm-creds.yaml, which contains just the username and
# password for the helm repo you wish to use to get the helm charts.
#
targetlabel     = 'Target'
prefzonelabel   = 'PreferredZones'
nodecountlabel  = 'NodeCount'
appchartvlabel  = 'AppChartVersion'
oprchartvlabel  = 'OperatorChartVersion'
tlscoordlabel   = 'RequireCoordTls'

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

    appchartversion = myvars[appchartvlabel] # AppChartVersion
    oprchartversion = myvars[oprchartvlabel] # OprChartVersion
    nodeCount       = myvars[nodecountlabel] # NodeCount
    tlscoord        = myvars[tlscoordlabel] # RequireCoordTls

    requireKey("AwsInstanceTypes", myvars)
    requireKey("AwsSmallInstanceType", myvars)
    requireKey("AzureVmTypes", myvars)
    requireKey("AzureSmallVmType", myvars)
    requireKey("GcpMachineTypes", myvars)
    requireKey("GcpSmallMachineType", myvars)

    helm_repo_name     = myvars["HelmRepo"]
    helm_repo_location = myvars["HelmRepoLocation"]

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
# ChartVersion.
#
def check_chart_version(label, vers):
    components = vers.split('.')
    if len(components) != 3 or not all(map(str.isdigit, components)):
        sys.exit(f'The {label} in {myvarsf} field must be of the form '
                 f'x.y.z, all numbers; {vers} is not of a valid form')

check_chart_version(appchartvlabel, appchartversion)
check_chart_version(oprchartvlabel, oprchartversion)

#
# NodeCount
#
# The yaml files for the coordinator and worker specify they should be on
# different nodes, so we need a 2-node cluster at minimum.
if nodeCount < minNodes:
    sys.exit(f"Must have at least {minNodes} nodes; {nodeCount} set for "
             f"{nodecountlabel} in {myvarsf}.")

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

templates = {}
releases = {}
charts = {}

operator = 'operator'
# no template for an operator!
releases[operator] = f'operator-{shortname}'
charts[operator] = 'hazelcast-platform-operator'

crds = ['cluster', srvnm_manctr]
for crd in crds:
    templates[crd] = f'{crd}_crd_v.yaml'

# Portfinder service

class Service:
    def __init__(self, name: str, lcl_port: int, rmt_port: int, tls: bool):
        self.name = name
        self.lcl_port = lcl_port
        self.rmt_port = rmt_port
        self.tls = tls

    def get_url(self):
        if self.tls:
            scheme = "https"
        else:
            scheme = "http"
        return f'{scheme}://{self.name}.{domain}:{self.lcl_port}'

class Services:
    def __init__(self):
        svcs_list: list[Service] = [
                # FIXME tls should be enabled for manctr port 8443 it seems;
                # but when I do so, I get this error back from requests.get:
                # [SSL] record layer failure (_ssl.c:1006)
                Service(srvnm_manctr, 8443, 443, tls=False),
                Service('cluster', 5701, 5701, tls=tlsenabled())
                ]
        # Cluster services are more limited
        self.clust_svcs: dict[str, Service] = { i.name: i for i in svcs_list }

        # Total list of services includes the K8S API service
        self.svcs: dict[str, Service] = self.clust_svcs | {
                'apiserv': Service('apiserv', 2153, 443, tls=True)
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

svcs = Services()

def random_string(length: int) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k = length))

def tmp_filename(prefix: str, ext: str, my_tmp_dir: str = "", random: bool = False) -> str:
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
        similar = f"{tmp_dir}/{root}.*\.{ext}"
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
        svc = svcs.get(svc_name)
        url = svc.get_url()
        if svc_name == srvnm_manctr:
            url += '/cluster-connections'
            r = requests.get(url, verify=svc.tls, timeout=5)
            return r.status_code == 200
        else:
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
        print(self.command)
        self.p = subprocess.Popen(self.command.split())
        assert self.p is not None
        out.announce("Created tunnel " + str(self))

    def __del__(self):
        out.announce("Terminating tunnel " + str(self))
        if ns.summarise_ssh_tunnels:
            print(self.command)
        assert self.p is not None
        self.p.terminate()

    def __str__(self):
        tgtname = self.shortname
        if len(self.raddr) < 16:
            tgtname = "[{n}]{h}".format(n = self.shortname, h = self.raddr)
        return "{l} -> {ra}:{rp} (PID {p})".format(l = self.lport, ra =
                                                   tgtname, rp = self.rport, p = self.p.pid if self.p else "?")

    def __enter__(self):
        print(f'Tunnel OPENED: {self}')
        return self

    def __exit__(self, *_):
        print(f'Tunnel CLOSED: {self}')
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

    # Now that the tunnel is in place, update our kubecfg with the address to
    # the tunnel, keeping everything else in place
    updateKubeConfig()

    # Ensure that we can talk to the api server
    out.announce("Waiting for api server to respond")
    out.spinWait(waitUntilApiServerResponding)

    return tun

def ensure_cluster_is_started(skipClusterStart: bool,
                              my_pub_ip: ipaddress.IPv4Address,
                              my_ssh_pub_key: str) -> tuple[Tunnel, dict]:
    env = {"ClusterName":         clustname,
           "Domain":              domain,
           "InstanceTypes":       instanceTypes,
           "MaxPodsPerNode":      maxpodpnode,
           "MyCIDR":              mySubnetCidr,
           "MyPublicIP":          my_pub_ip,
           'NetwkName':           netwkname,
           "NodeCount":           nodeCount,
           "SmallInstanceType":   smallInstanceType,
           "SshPublicKey":        my_ssh_pub_key,
           "Region":              region,
           "Target":              target,
           "UserName":            username,
           "ShortName":           shortname,
           "Zone":                zone}

    assert target in clouds

    if target == "az":
        env["ResourceGroup"] = resourcegrp
    elif target == "gcp":
        env["GcpProjectId"] = gcpproject
        env["GcpAccount"] = gcpaccount

    parameteriseTemplate(tfvars, tfdir, env)

    # The terraform run. Perform an init, then an apply.
    if not skipClusterStart:
        out.announce('running terraform init & apply')
        runStdout(f"{tf} init -upgrade -input=false".split())
        runStdout(f"{tf} apply -auto-approve -input=false".split())

    # Get variables returned from terraform run
    env = get_output_vars()

    # Start up ssh tunnels via the bastion, so we can run kubectl locally from
    # the workstation
    tun = setup_bastion_tunnel(env['bastion_address'], env['k8s_api_server'])

    # Don't continue until all nodes are ready
    out.announce("Waiting for nodes to come online")
    out.spinWait(lambda: waitUntilNodesReady(nodeCount))

    # Don't continue until all K8S system pods are ready
    out.announce("Waiting for K8S system pods to come online")
    out.spinWait(lambda: waitUntilPodsReady("kube-system"))
    return tun, env

# Pods sometimes get stuck in Terminating phase after a helm upgrade.
# Kill these off immediately to save time and they will restart quickly.
def killAllTerminatingPods() -> None:
    lines = runCollect(f"{kubens} get pods --no-headers".split()).splitlines()
    for line in lines:
        col = line.split()
        name = col[0]
        status = col[2]
        if status == "Terminating":
            r = runTry(f"{kubens} delete pod {name} --grace-period=60".split())
            if r.returncode == 0:
                print(f"Terminated pod {name}")

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

def start_tunnel_to_lbs(bastionIp: str) -> tuple[list[Tunnel], dict[str, str]]:
    tuns: list[Tunnel] = []

    out.announce("Waiting for pods to be ready")
    expectedContainers = numberOfContainers(nodeCount)
    out.spinWait(lambda: waitUntilPodsReady(namespace, expectedContainers))

    out.announce("Waiting for deployments to be available")
    expectedReplicas = numberOfReplicas(nodeCount)
    out.spinWait(lambda: waitUntilDeploymentsAvail(namespace, expectedReplicas))

    # now the load balancers need to be running with their IPs assigned
    out.announce("Waiting for load-balancers to launch")
    out.spinWait(lambda: waitUntilLoadBalancersUp(svcs.get_clust_svc_names(),
                                                  namespace))

    #
    # Get the DNS name of the load balancers we've created
    #
    lbs = getLoadBalancers(svcs.get_clust_svc_names(), namespace)

    # we should have a load balancer for every service we'll forward
    assert len(lbs) == len(svcs.get_clust_svc_names())
    for svcname in svcs.get_clust_svc_names():
        assert svcname in lbs
        tuns.append(Tunnel(svcname,
                           ipaddress.IPv4Address(bastionIp),
                           svcs.get_lcl_port(svcname),
                           lbs[svcname],
                           svcs.get_rmt_port(svcname)))

    # make sure the load balancers are actually responding
    out.announce("Waiting for load-balancers to start responding")
    out.spinWait(lambda: waitUntilLoadBalancersUp(svcs.get_clust_svc_names(),
                                                  namespace,
                                                  checkConnectivity = True))

    return tuns, lbs

def convert_zulu_time_to_timestamp(datetimestr: str) -> float:
    # Google sometimes returns UTC dates with military/Zulu format; standardise
    # these here so we can parse them uniformly
    if datetimestr.endswith('Z'):
        datetimestr = datetimestr[:-1] + "+00:00"
    return datetime.timestamp(datetime.fromisoformat(datetimestr))

def install_secrets_into_k8s(secrets_to_add: dict[str, dict[str, str]]) \
        -> dict[str, str]:
    out.announce('Ensuring secrets are installed in K8S')
    env = {}
    installed_secrets = {}
    if secrets_to_add:
        x = runCollect(kubens.split() +
                       ['get', 'secrets',
                        '-o=jsonpath={range $.items[*].metadata}'
                        '{.name}{" "}{.creationTimestamp}{" "}{end}'])
        if x:
            s = x.split()
            z = zip(s[0::2], s[1::2])
            installed_secrets = {x: y for x, y in z}

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
            runIgnore(f'{kubens} delete secret {secret_to_add_name}'.split())
        else:
            print(f'Installing secret "{secret_to_add_name}" from {file}')

        # If this isn't a cert group, then install the secret normally. If
        # this is a cert group, and we are terminating TLS at an
        # ingress-based LB, then we need to install a secret that we'll use
        # in the helm chart with the LB.
        runIgnore(f'{kubens} create secret generic {secret_to_add_name} '
                  f'--from-file={file_arg}'.split())

    return env

def helmTry(cmd: str) -> subprocess.CompletedProcess:
    return runTry(["helm"] + cmd.split())

def helm(cmd: str) -> None:
    runStdout(["helm"] + cmd.split())

def helmGet(cmd: str) -> str:
    return runCollect(["helm"] + cmd.split())

def helm_set_up_repo(helm_repo_name: str, helm_repo_location: str) -> None:
    if (r := helmTry("version")).returncode != 0:
        sys.exit("Unable to run helm. Is it installed? Failing out.")

    # There is a bug in helm repo list, wherein it inconsistently returns
    # nonzero error codes when there are no repos installed. So just try to
    # fast-path the common case where the repo is already installed, and
    # otherwise try to install.
    if (r := helmTry("repo list -o=json")).returncode == 0:
        repos = [x["name"] for x in json.loads(r.stdout)]
        if helm_repo_name in repos:
            # Unfortunately, helm repo update returns a 0 error code even when
            # it fails. So we actually have to collect the output and look to
            # see if it failed. :-( If it fails, then just remove the repo and
            # re-install it.
            out.announce(f'Updating helm repo {helm_repo_name}')
            output = helmGet("repo update --fail-on-repo-update-fail")
            if "Update Complete. ⎈Happy Helming!⎈" in output:
                print("Upgrade of repo succeeded")
                return

            out.announce(f'Update of repo failed. Removing '
                         f'repo {helm_repo_name}')
            helm(f'repo remove {helm_repo_name}')

    crepouser = ''
    crepopass = ''
    helm(f'repo add {crepouser} {crepopass} '
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

def k8s_create_namespace() -> None:
    if namespace not in helmGetNamespaces():
        runStdout(f'{kube} create namespace {namespace}'.split())
    runStdout(f'{kube} config set-context --namespace={namespace} '
              '--current'.split())

def helm_delete_namespace() -> None:
    if namespace in helmGetNamespaces():
        out.announce(f"Deleting namespace {namespace}")
        runStdout(f'{kube} delete --grace-period=60 namespace {namespace}'.split())
    runStdout(f"{kube} config set-context --namespace=default "
              "--current".split())

def helmGetReleases() -> dict:
    rls = {}
    try:
        rlsj = json.loads(helmGet(f"{helmns} list -ojson"))
        rls = { r["name"]: r["chart"] for r in rlsj }
    except CalledProcessError:
        print("No helm releases found.")
    return rls

def helmWhichChartInstalled(module: str) -> Optional[str]:
    chart = None
    release = releases[module] # Get release name for module name
    installed = helmGetReleases()
    if release in installed:
        chart = installed[release] # Get chart for release
    return chart

def helmInstallOperator(module: str, env: dict = {}) -> None:
    chart = helmWhichChartInstalled(module)
    newchart = charts[module] + "-" + oprchartversion # which one to install?

    if chart is None: # Nothing installed yet, so we need to install
        out.announce("Installing chart {c} as {r}".format(c = newchart, r =
                                                          releases[module]))
        helm("{h} install {r} {w}/{c} --version {v}"
             .format(h=helmns, r=releases[module], w=helm_repo_name, c=charts[module],
                     v=oprchartversion))
    # If either the chart values file changed, or we need to update to a
    # different version of the chart, then we have to upgrade
    elif chart != newchart:
        astr = "Upgrading release {}".format(releases[module])
        if chart != newchart:
            astr += ": {oc} -> {nc}".format(oc = chart, nc = newchart)
        out.announce(astr)
        helm("{h} upgrade {r} {w}/{c} --version {v}"
             .format(h=helmns, r=releases[module], w=helm_repo_name, c=charts[module],
                     v=oprchartversion))
    else:
        print(f"{chart} values unchanged ➼ avoiding helm upgrade")

def KubeApplyCrd(crd: str, env: dict = {}) -> None:
    # Ignore changes, apply every time
    _, yamltmp = parameteriseTemplate(templates[crd], tmpdir, env)

    out.announce(f'Applying CRD "{crd}"')
    runStdout(f'{kubens} apply -f {yamltmp}'.split())

def KubeDeleteCrd(crd: str, env) -> None:
    # Generate filename of tmp file where CRD lives
    yamltmp, _, _ = convert_template_to_tmpname(templates[crd])

    if bbio.readableFile(yamltmp):
        out.announce(f'Deleting CRD "{crd}"')
        runStdout(f'{kubens} delete --grace-period=60 --ignore-not-found=true -f {yamltmp}'.split())

def helmUninstallRelease(release: str) -> None:
    helm(f"{helmns} uninstall {release}")

def helm_create_operator_and_crds(env: dict[str, str]) -> None:
    helmInstallOperator(operator, env)
    for crd in crds:
        KubeApplyCrd(crd, env)

    # Speed up the deployment of the updated pods by killing the old ones
    killAllTerminatingPods()

def delete_all_services(lbs: dict[str, str]) -> bool:
    # Explicitly deleting services gets rid of load balancers, which eliminates
    # a race condition that Terraform is susceptible to, where the ELBs created
    # by the load balancers endure while the cluster is destroyed, stranding
    # the ENIs and preventing the deletion of the associated subnets
    # https://github.com/kubernetes/kubernetes/issues/93390
    out.announce("Deleting all k8s services")
    if len(lbs) == 0:
        print("No LBs running.")
    else:
        print("Load balancers before attempt to delete services: " + ", ".join(lbs.keys()))
    runStdout(f"{kubens} delete --grace-period=60 svc --all".split())
    lbs_after = getLoadBalancers(svcs.get_clust_svc_names(), namespace)
    if len(lbs_after) == 0:
        print("No load balancers running after service delete.")
        return True
    else:
        print("# WARN Load balancers running after service delete! " +
              str(lbs_after))
        print("# WARN This may cause dependency problems later!")
        return False

def helm_delete_crds_and_operator():
    for release, chart in helmGetReleases().items():
        try:
            out.announce(f"Uninstalling chart {chart}")
            helmUninstallRelease(release)
        except CalledProcessError as e:
            print(f"Unable to uninstall release {release}: {e}")
    killAllTerminatingPods()

def svcStart(secrets: dict[str, dict[str, str]],
             skipClusterStart: bool = False) -> tuple[list[Tunnel], str]:
    tuns: list[Tunnel] = []
    env: dict[str, str] = {}

    # Get my public IP and SSH public key
    #
    my_pub_ip = get_my_pub_ip()
    my_ssh_pub_key = get_ssh_pub_key()

    #
    # Infrastructure first. Create the cluster using Terraform.
    #
    with Timer('set up infrastructure'):
        tun, env = ensure_cluster_is_started(skipClusterStart, my_pub_ip,
                                             my_ssh_pub_key)
        tuns.append(tun)

    bastion = env['bastion_address']

    # Do this first so all resources install into the namespace
    with Timer('set up K8S and Helm'):
        k8s_create_namespace()

        env |= {
            'AppChartVersion': appchartversion,
            'NodeCount': nodeCount,
            'SrvNmCluster': srvnm_cluster,
            'SrvNmManctr': srvnm_manctr
            } | install_secrets_into_k8s(secrets)

        # Set up the Helm repo if not already done
        helm_set_up_repo(helm_repo_name, helm_repo_location)

    with Timer('deploy K8S resources'):
        helm_create_operator_and_crds(env)
        # Wait for pods & LBs to become ready
        # Set up port forward tunnels for LBs
        new_tuns, lbs = start_tunnel_to_lbs(bastion)

    # Add CNAMES or A records for DNS for new LBs
    set_dns_for_lbs(env['zone_id'], lbs)

    tuns.extend(new_tuns)
    return tuns, bastion

def svcStop(onlyEmptyNodes: bool = False) -> None:
    # Re-establish the tunnel with the bastion to allow our commands to flow
    # through to the K8S cluster.
    out.announce("Re-establishing bastion tunnel")
    lbs_cleaned = False

    try:
        env = get_output_vars()
        zone_id = env['zone_id']
        bastion_ip = env['bastion_address']
        k8s_server_name = env['k8s_api_server']

        # We need the bastion tunnel up in order to fetch the LBs
        with setup_bastion_tunnel(bastion_ip, k8s_server_name):
            # NOTE: DNS *must* be removed since Terraform will complain about any
            # records it didn't create at the time the zone is destroyed.
            lbs = getLoadBalancers(svcs.get_clust_svc_names(), namespace)
            try:
                set_dns_for_lbs(zone_id, lbs, delete=True)
            except CalledProcessError:
                print('Unable to delete DNS record sets (do they exist?)')

            with Timer('teardown of K8S resources'):
                # tunnel established. Now delete things in reverse order to how
                # they were created.

                for crd in crds:
                    KubeDeleteCrd(crd, env)
                helm_delete_crds_and_operator()

                # Make sure to get rid of all services, in case they weren't
                # already removed. We need to make sure we don't leak LBs.
                lbs_after_helm_uninstall = \
                        getLoadBalancers(svcs.get_clust_svc_names(), namespace)
                lbs_cleaned = delete_all_services(lbs_after_helm_uninstall)
                helm_delete_namespace()
    except (MissingTerraformOutput):
        out.announce('Terraform objects partly or fully destroyed')

    if onlyEmptyNodes:
        return

    if not lbs_cleaned:
        out.announceBox(textwrap.dedent("""\
                Your bastion host is not responding. I will try to destroy your
                terraform without unloading your pods, but you might have
                trouble on the destroy with leaked LBs."""))

    out.announce(f"Ensuring cluster {clustname} is deleted")
    with Timer('stopping cluster'):
        runStdout(f"{tf} destroy -auto-approve".split())

def fqdnToDc(fqdn: str) -> str:
    dcs = fqdn.split('.')
    return ",".join([f"dc={d}" for d in dcs])

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
            f"Cluster: {nodeCount} × {instanceTypes[0]}"]

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
                output = runCollect("openssl verify -untrusted {ch} {c}".format(ch
                                                                                = values["chain"], c = values["cert"]).split()).splitlines()
                if output[-1] == values['cert'] + ': OK':
                    print('Verified certificate ' + values["cert"])
            except CalledProcessError:
                print("Unable to verify cert {c} & chain {ch}".format(c =
                                                                      values["cert"], ch = values["chain"]))
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
                       r"((?=.{1,255}$)[A-Za-z0-9]{1,63})"
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

    started = False

    if ns.command in ("stop", "restart"):
        svcStop(ns.empty_nodes)

    tuns: list[Tunnel] = []

    y = getCloudSummary()
    if ns.command in ("start", "restart"):
        tuns, bastion_ip = svcStart(secrets, ns.skip_cluster_start)
        started = True
        out.announceBox(f'Your {rsaPub} public key has been installed into the '
                        'bastion server, so you can ssh there now '
                        f'(user "{bastionuser}").')
        y += (['Service is started on:'] +
              [f'[{s.name}] {s.get_url()}' for s in svcs.get_clust_all()])
    else:
        y += ['Service is stopped']
    out.announceLoud(y)
    if started:
        input("Press return key to quit and terminate tunnels!")

main()
