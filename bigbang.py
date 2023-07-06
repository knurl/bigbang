#!/usr/bin/env python

# modules expressly for bigbang
from run import run, runShell, runTry, runStdout, runCollect, retryRun
from capcalc import planWorkerSize, numberOfReplicas, numberOfContainers
import sql, tpc, creds, bbio, ready # local imports
from cmdgrp import CommandGroup, SqlCommandGroup
from out import *

import os, hashlib, argparse, sys, pdb, textwrap, requests, json, re
import subprocess, ipaddress, glob, threading, time, random, io
import yaml # type: ignore
import atexit, psutil # type: ignore
from subprocess import CalledProcessError
from typing import List, Tuple, Iterable, Callable, Optional, Any, Dict, Set
from urllib.parse import urlparse
import jinja2
from jinja2.meta import find_undeclared_variables

# Do this just to get rid of the warning when we try to read from the
# api server, and the certificate isn't trusted
from urllib3 import disable_warnings, exceptions # type: ignore
disable_warnings()

# Suppress info-level messages from the requests library
import logging
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

#
# Global variables.
#

# Paths or path sub-components
templatedir = bbio.where("templates")
tmpdir      = "/tmp"
ingressname = "sb-ingress"
rsa         = os.path.expanduser("~/.ssh/id_rsa")
rsaPub      = os.path.expanduser("~/.ssh/id_rsa.pub")
knownhosts  = os.path.expanduser("~/.ssh/known_hosts")
myvarsbf    = 'my-vars.yaml'
myvarsf     = bbio.where(myvarsbf)
helmcredsbf = 'helm-creds.yaml'
helmcredsf  = bbio.where(helmcredsbf)
sfdccredsbf = 'sfdc-creds.yaml' # don't find FQP yet as SFDC is optional
tfvars      = "variables.tf" # basename only, no path!
hostsf      = "/etc/hosts"
bastlaunchf = bbio.where("bastlaunch.sh")
ldapsetupf  = bbio.where("install-slapd.sh")
ldaplaunchf = bbio.where("ldaplaunch.sh")

# Different cloud targets
clouds = ("aws", "az", "gcp")

# Hosts, ports, services and associated creds
dbports       = { "mysql": 3306, "postgres": 5432 }
trinouser     = "starburst_service"
trinopass     = "test"
localhost     = "localhost"
localhostip   = "127.0.0.1"
domain        = "az.starburstdata.net"
starburstfqdn = "starburst." + domain
ldapfqdn      = "ldap." + domain
bastionfqdn   = "bastion." + domain
keystorepass  = "test123"

# System catalogs
syscat    = "system"
evtlogcat = "evtlog" # catalog name for event logger

# Regular catalogs
bqcat        = 'bq'
redshiftcat  = 'redshift'
sfdccat      = "sfdc"
synapseslcat = 'synapse_sl'
synapsenpcat = 'synapse_pool'
s3cat        = 's3'
adlscat      = 'adls'
gcscat       = 'gcs'
deltacat     = 'delta'

# Data source names and credentials
dbschema    = "s"
dbuser      = "starburstuser"
dbpwd       = "a029fjg!>dugBiO8"
cachetsrsch = 'cache_tsr'
cachemvsch  = 'cache_mv'
mvsch       = 'mv'
cachesch    = {cachetsrsch, cachemvsch, mvsch}
tsrsch      = {cachetsrsch}
dbevtlog    = "evtlog" # event logger PostgreSQL database
dbhms       = "hms" # Hive metastore persistent database
dbcachesrv  = "cachesrv" # cache service persistent database

# K8S / Helm
namespace   = "starburst"
kube        = "kubectl"
kubens      = f"{kube} -n {namespace}"
helmns      = f"-n {namespace}"
minNodes    = 3 # See getMinNodeResources(); allows rolling upgrades
maxpodpnode = 32

# TPC-H, -DS and scale sets
minbucketsize  = 1 << 12
tpchbigsch  = tpc.scale_sets.smallest()
tpchsmlsch  = tpchbigsch
tpcdsbigsch = tpc.scale_sets.smallest()
tpcdssmlsch = tpcdsbigsch

#
# Secrets
# 
secrets: dict[str, dict[str, str]] = {}
secretsbf    = "secrets.yaml"
secretsf     = bbio.where(secretsbf)

#
# Start of execution. Handle commandline args.
#

p = argparse.ArgumentParser(description=
        """Create your own Starbust demo service in AWS, Azure or GCP,
        starting from nothing. It's zero to demo in 20 minutes or less. You
        provide your target cloud, zone/region, version of software, and your
        cluster size and instance type, and everything is set up for you,
        including Starburst, multiple databases, and a data lake. The event
        logger and Starburst Insights are set up too. This script uses
        terraform to set up a K8S cluster, with its own VPC/VNet and K8S
        cluster, routes and peering connections, security, etc. It's designed
        to allow you to control the new setup from your laptop using a bastion
        server.""")

p.add_argument('-c', '--skip-cluster-start', action="store_true",
        help="Skip checking to see if cluster needs to be started.")
p.add_argument('-e', '--empty-nodes', action="store_true",
        help="Unload k8s cluster only. Used with stop or restart.")
p.add_argument('-i', '--disable-bastion-fw', action="store_true",
        help="Disable bastion firewall—only protection will be ssh!")
p.add_argument('-l', '--dont-load', action="store_true",
        help="Don't load databases with tpc data.")
p.add_argument('-n', '--node-layout', action="store_true",
        help="Show how containers lay out in nodes.")
p.add_argument('-r', '--drop-tables', action="store_true",
        help="Drop all tables before loading with tpc data.")
p.add_argument('-s', '--summarise-ssh-tunnels', action="store_true",
        help="Summarise the ssh tunnels on exit.")
p.add_argument('-t', '--target', action="store",
        help="Force cloud target to specified value.")
p.add_argument('-z', '--zone', action="store",
        help="Force zone/region to specified value.")
p.add_argument('-B', '--bastion', action="store",
        type=ipaddress.IPv4Address,
        help="Specify upstream bastion IP address, if this is a downstream "
        "instance for Stargate.")
p.add_argument('-A', '--azaddrs', nargs=2, action="store",
        type=ipaddress.IPv4Address,
        metavar=('bastionIP', 'starburstIP'),
        help="Gather the downstream Azure bastion IP and starburst LB IP as a "
        "pair, if this is an upstream instance for Stargate.")
p.add_argument('-G', '--gcpaddrs', nargs=2, action="store",
        type=ipaddress.IPv4Address,
        metavar=('bastionIP', 'starburstIP'),
        help="Gather the downstream GCP bastion IP and starburst LB IP as a "
        "pair, if this is an upstream instance for Stargate.")
p.add_argument('command',
        choices = ["start", "stop", "restart", "status"],
        help="""Command to issue for demo services.
           start/stop/restart: Start/stop/restart the demo environment.
           status: Show whether the environment is running or not.""")

p.add_argument('-P', '--progmeter-test', action="store_true",
        help=argparse.SUPPRESS)

ns = p.parse_args()

# Options which can only be used with start (or restart)
if ns.command not in ("start", "restart"):
    v = vars(ns)
    for switch in {"dont_load", "skip_cluster_start", "drop_tables"}:
        if switch in v and v[switch] == True:
            p.error(f"{switch} is only used with start (or restart)")

# Options which can only be used with stop (or restart)
if ns.command not in ("stop", "restart") and ns.empty_nodes:
    p.error("empty_nodes is only used with stop or restart")

# Mutually exclusive options
if ns.bastion and (ns.azaddrs or ns.gcpaddrs):
    p.error("Must be either upstream or downstream for Stargate, not both!")

#
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd config file,
# very small, called ./helm-creds.yaml, which contains just the username and
# password for the helm repo you wish to use to get the helm charts.
#
targetlabel     = 'Target'
prefzonelabel   = 'PreferredZones'
nodecountlabel  = "NodeCount"
chartvlabel     = "ChartVersion"
tlscoordlabel   = "RequireCoordTls"
ingresslblabel  = "IngressLoadBalancer"
authnldaplabel  = "AuthNLdap"
captypelabel    = "CapacityType"
salesforcelabel = "SalesforceEnabled"
perftestlabel   = "PerformanceTesting"
capacitytypes   = {"Spot", "OnDemand"}
mysqlenlabel    = 'MySqlEnabled'
postgresenlabel = 'PostgreSqlEnabled'

try:
    with open(myvarsf) as mypf:
        myvars = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read user variables file {e}")

def requireKey(key: str, d: dict[str, Any]):
    if not key in d:
        raise KeyError(key)

try:
    # Email
    email = myvars['Email']

    # Target
    target = ns.target if ns.target else myvars[targetlabel]

    # Zone - If from myvars, take first choice from preferred list
    zone = ns.zone if ns.zone else myvars[prefzonelabel][target][0]

    chartversion = myvars[chartvlabel] # ChartVersion
    nodeCount    = myvars[nodecountlabel] # NodeCount
    ingresslb    = myvars[ingresslblabel] # ExternalLoadBalancer
    tlscoord     = myvars[tlscoordlabel] # RequireCoordTls
    authnldap    = myvars[authnldaplabel] # AuthNLdap

    nobastionfw  = myvars["DisableBastionFw"] or ns.disable_bastion_fw
    myvars["DisableBastionFw"] = nobastionfw
    sfdcenabled  = myvars[salesforcelabel] # SalesforceEnabled
    requireKey(mysqlenlabel, myvars)
    requireKey(postgresenlabel, myvars)

    perftest     = myvars[perftestlabel] # PerformanceTesting

    # Keep the cache service enabled normally, to support materialised views.
    # Only disable if it we are running in performance mode, where we want to
    # reserve the full memory for performance testing (and not the cache
    # service helm chart)
    cachesrv_enabled = not perftest

    capacityType = myvars[captypelabel]

    requireKey("AwsInstanceTypes", myvars)
    requireKey("AwsPerfInstanceTypes", myvars)
    requireKey("AwsSmallInstanceType", myvars)
    requireKey("AwsDbInstanceType", myvars)
    requireKey("AzureVmTypes", myvars)
    requireKey("AzureSmallVmType", myvars)
    requireKey("AzureDbVmType", myvars)
    requireKey("GcpMachineTypes", myvars)
    requireKey("GcpSmallMachineType", myvars)
    requireKey("GcpDbMachineType", myvars)

    mysql_enabled = myvars[mysqlenlabel]
    postgres_enabled = myvars[postgresenlabel]

    repo         = myvars["HelmRepo"]
    helmregistry = myvars['HelmRegistry']
    repoloc      = myvars["HelmRepoLocation"]
except KeyError as e:
    print(f"Unspecified configuration parameter {e} in {myvarsf}.")
    sys.exit(f"Consider running a git diff {myvarsf} to ensure no "
            "parameters have been eliminated.")

# Set up name of hive catalog according to target cloud
if target == 'aws':
    hivecat   = s3cat
elif target == 'az':
    hivecat   = adlscat
elif target == 'gcp':
    hivecat   = gcscat

lakecats = { hivecat, deltacat }
gluecats = { s3cat, deltacat } # > 1 catalogs both using Glue
sharedcats = gluecats | {bqcat} # Catalogs shared by > 1 user

# Catalogs that require casting for CTAS
unsupported_types = {bqcat: [('char(%)', 'varchar'),
                             ('decimal(%,%)', 'double')],
                     deltacat: [('char(%)', 'varchar')]}

#
# Stargate
#
upstreamSG = False
azaddrs = None
gcpaddrs = None
if ns.azaddrs:
    upstreamSG = True
    azaddrs = { "bastion": ns.azaddrs[0], "starburst": ns.azaddrs[1] }
if ns.gcpaddrs:
    upstreamSG = True
    gcpaddrs = { "bastion": ns.gcpaddrs[0], "starburst": ns.gcpaddrs[1] }

downstreamSG = False
upstrBastion = None
if ns.bastion:
    try:
        upstrBastion = ipaddress.IPv4Address(ns.bastion)
        downstreamSG = True
    except ValueError:
        sys.exit(f"{ns.bastion} is not a valid IP address")

assert not (upstreamSG and downstreamSG) # mutually exclusive

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
                    Region {awsregion} specified in your {creds.awsconfig} "
                    "doesn't match region {region} set in your {myvarsf} file."
                    "Cannot continue. Please ensure these match and
                    re-run."""))

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
components = chartversion.split('.')
if len(components) != 3 or not all(map(str.isdigit, components)):
    sys.exit(f"The {chartvlabel} in {myvarsf} field must be of the form "
            f"x.y.z, all numbers; {chartversion} is not of a valid form")

#
# NodeCount
#
# The yaml files for the coordinator and worker specify they should be on
# different nodes, so we need a 2-node cluster at minimum.
if nodeCount < minNodes:
    sys.exit(f"Must have at least {minNodes} nodes; {nodeCount} set for "
            f"{nodecountlabel} in {myvarsf}.")

if ingresslb and tlscoord:
    sys.exit(f"{ingresslblabel} and {tlscoordlabel} are mutually exclusive.")

if (upstreamSG or downstreamSG) and not (tlscoord or ingresslb):
    sys.exit(f"Stargate mode requires {tlscoordlabel} to be enabled")

def tlsenabled() -> bool: return ingresslb or tlscoord

if authnldap and not tlsenabled():
    sys.exit(f"{authnldaplabel} requires a TLS-protected connection")

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
# Now, read the credentials file for helm ("./helm-creds.yaml"), also found in
# this directory.  This is the 2nd configuration file one needs to edit.
#
try:
    with open(helmcredsf) as mypf:
        helmcreds = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read helm credentials file {e}")

try:
    repouser     = helmcreds["HelmRepoUser"]
    repopass     = helmcreds["HelmRepoPassword"]
except KeyError as e:
    sys.exit(f"Unspecified configuration parameter {e} in {helmcredsf}")

#
# Now, read the credentials file for Salesforce ("./sfdc-creds.yaml"), also
# found in this directory.  This is the 3rd configuration file one needs to
# edit, but only if Salesforce access is desired.
#
if sfdcenabled:
    sfdccredsf  = bbio.where(sfdccredsbf)
    try:
        with open(sfdccredsf) as mypf:
            sfdccreds = yaml.load(mypf, Loader = yaml.FullLoader)
    except IOError as e:
        sys.exit(f"Couldn't read Salesforce credentials file {e}")

    try:
        sfdcuser  = sfdccreds['SalesforceUser']
        sfdcpass  = sfdccreds['SalesforcePassword']
        sfdctoken = sfdccreds['SalesforceSecurityToken']

    except KeyError as e:
        print(f"Unspecified configuration parameter {e} in {sfdccredsf}.")

# Performance testing
if perftest:
    if target != "aws":
        sys.exit('Performance mode supported with AWS only')

    if tlsenabled():
        sys.exit('Performance mode cannot be used with TLS')

    if capacityType != 'OnDemand':
        sys.exit('Performance mode supported with on-demand instances only')

    if mysql_enabled or postgres_enabled:
        sys.exit('Performance mode must have MySQL and PostgreSQL disabled')

#
# Determine which instance types we're using for this cloud target
#
instanceTypes: list[str] = []
smallInstanceType = ""
dbInstanceType = ""

if target == "aws":
    if perftest:
        instanceTypes = myvars["AwsPerfInstanceTypes"]
    else:
        instanceTypes = myvars["AwsInstanceTypes"][capacityType]
    smallInstanceType = myvars["AwsSmallInstanceType"]
    dbInstanceType    = myvars["AwsDbInstanceType"]
elif target == "az":
    instanceTypes     = myvars["AzureVmTypes"][capacityType]
    smallInstanceType = myvars["AzureSmallVmType"]
    dbInstanceType    = myvars["AzureDbVmType"]
elif target == "gcp":
    instanceTypes     = myvars["GcpMachineTypes"][capacityType]
    smallInstanceType = myvars["GcpSmallMachineType"]
    dbInstanceType    = myvars["GcpDbMachineType"]
else:
    sys.exit("Cloud target '{t}' specified for '{tl}' in '{m}' not one of "
            "{c}".format(t = target, tl = targetlabel, m = myvarsf,
                c = ", ".join(clouds)))

assert capacityType in ("OnDemand", "Spot")
assert len(instanceTypes) > 0
assert capacityType == "Spot" or len(instanceTypes) == 1

#
# Create some names for some cloud resources we'll need
#
clustname = longname + "-cl"
bucket = longname + "-bk"
storageacct = longname + "-sa"
resourcegrp = longname + "-rg"
netwkname = longname + '-net'

templates = {}
releases = {}
charts = {}
modules = ['enterprise']
if target != 'aws':
    modules.append('hive')
if cachesrv_enabled:
    modules.append('cache-service')
for module in modules:
    templates[module] = f"{module}_v.yaml"
    releases[module] = f"{module}-{shortname}"
    charts[module] = f"starburst-{module}"

# Portfinder service

services = ['starburst']
if cachesrv_enabled:
    services.append('cache-service')
svcports    = {
        "cache-service": {"local": 8180, "remote": 8180},
        "apiserv": {"local": 2153, "remote": 443}
        }
if tlsenabled():
    svcports |= {"ldaps": {"local": 8636, "remote": 636}}
    if ingresslb:
        svcports |= {"starburst": {"local": 8443, "remote": 443}}
    else:
        svcports |= {"starburst": {"local": 8443, "remote": 8443}}
else:
    svcports |= {"starburst": {"local": 8080, "remote": 8080}}

portoffset = { "aws": 0, "az": 1, "gcp": 2 }

# Local connections are on workstation, so offset to avoid collision
def getLclPortSG(service: str, target: str) -> int:
    return svcports[service]["local"] + portoffset[target]

def getLclPort(service: str) -> int:
    return getLclPortSG(service, target)

# Remote connections are all to different machines, so they don't need offset
def getRmtPort(service: str) -> int:
    return svcports[service]["remote"]

def appendToFile(filepath, contents) -> None:
    with open(filepath, "a+") as fh:
        fh.write(contents)

def replaceFile(filepath, contents) -> bool:
    newmd5 = hashlib.md5(contents.encode('utf-8')).hexdigest()
    root, ext = os.path.splitext(filepath)

    if os.path.exists(filepath):
        if not os.path.isfile(filepath):
            sys.exit("Please manually remove {filepath} and rerun")
        # We have an old file by the same name. Check the extension, as we only
        # embed the md5 and version in file formats that take comments, and
        # .json files don't take comments.
        if ext in (".yaml", ".tf"):
            with open(filepath) as fh:
                fl = fh.readline()
                if len(fl) > 0:
                    if match := re.match(r"# md5 ([\da-f]{32})", fl):
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
            if ext in (".yaml", ".tf"):
                fh.write(f"# md5 {newmd5}\n")
            fh.write(contents)
    except IOError as e:
        print(f"Couldn't write file {filepath} due to {e}")
        raise
    return True # wrote new file

def removeOldVersions(yamltmp: str, similar: str) -> None:
    old = glob.glob(similar)
    for f in old:
        if f == yamltmp:
            continue # skip the one we're about to write
        print(f"Removing old parameterised file {f}")
        os.remove(f)

def parameteriseTemplate(template: str, targetDir: str, varsDict: dict,
        undefinedOk: set[str] = set()) -> tuple[bool, str]:
    assert os.path.basename(template) == template, \
            f"YAML template {template} should be in basename form (no path)"
    root, ext = os.path.splitext(template)
    assert len(root) > 0 and len(ext) > 0

    # temporary file where we'll write the filled-in template
    yamltmp = f"{targetDir}/{root}-{shortname}{ext}"

    # if we're writing a Terraform file, make sure to clean up older,
    # similar-looking Terraform files as these will cause Terraform to fail
    if ext == ".tf":
        similar = f"{targetDir}/{root}-*{ext}"
        removeOldVersions(yamltmp, similar)

    # render the template with the parameters, and capture the result
    try:
        file_loader = jinja2.FileSystemLoader(templatedir)
        env = jinja2.Environment(loader = file_loader, trim_blocks = True,
                lstrip_blocks = True, undefined = jinja2.DebugUndefined)
        t = env.get_template(template)
        output = t.render(varsDict)
        ast = env.parse(output)
        undefined = find_undeclared_variables(ast)
        if len(undefined - undefinedOk) > 0:
            raise jinja2.UndefinedError(f"Undefined vars in {template}: "
                    f"{undefined}; undefinedOK = {undefinedOk}")
    except jinja2.TemplateNotFound as e:
        print(f"Couldn't read {template} from {templatedir} due to {e}")
        raise

    changed = replaceFile(yamltmp, output)
    return changed, yamltmp

def get_output_vars() -> dict:
    x = json.loads(runCollect(f"{tf} output -json".split()))
    env = {k: v["value"] for k, v in x.items()}
    if target == "aws":
        # Trim off everything on the AWS API server endpoint so that we're left
        # with just the hostname.
        ep = env["k8s_api_server"]
        u = urlparse(ep)
        assert u.scheme == None or u.scheme == "https"
        assert u.port == None or u.port == 443
        env["k8s_api_server"] = u.hostname

    sources = ["evtlog"]

    if cachesrv_enabled:
        sources.append('cachesrv')

    if postgres_enabled:
        sources.append('postgres')

    if mysql_enabled:
        sources.append('mysql')

    if target == "aws":
        sources.append('redshift')
    else:
        sources.append('hmsdb') # Azure and GCP need the HMS
        if target == 'az':
            sources += ['synapse_sl', 'synapse_pool']

    for db in sources:
        db_address = db + '_address'
        assert db_address in env

        # Normally we simply want to create a variable for the username of each
        # data source in our environment, equal to a fixed username. However,
        # for Azure we have to do something special, as it interposes a gateway
        # in front of the database that forwards connections from
        # username@hostname to username at hostname.
        db_user = db + '_user'
        env[db_user] = dbuser # we use the same username for all DB sources
        if target == "az":
            env[db_user] += "@" + env[db_address] # append DB address to user

    # Having set up storage, we've received some credentials for it that we'll
    # need later. For GCP, write out a key file that Hive will use to access
    # GCS. For Azure, just set a value we'll use for the starburst values file.
    if target == "gcp":
        replaceFile(secrets["gcskey"]["f"], env["object_key"])
    elif target == "az":
        env["adls_access_key"] = env["object_key"]

    return env

class KubeContextError(Exception):
    pass

def updateKubeConfig() -> None:
    # Phase I: Write in the new kubectl config file as-is
    announce(f"Updating kube config file")
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
    for l in c:
        columns = l.split()
        if columns[0] == "*":
            # get the cluster name
            cluster = columns[2]
            runStdout("kubectl config set clusters.{c}.server "
                    "https://{h}:{p}".format(c = cluster, h = localhost, p =
                        getLclPort("apiserv")).split())
            runStdout(f"kubectl config set-cluster {cluster} "
                    "--insecure-skip-tls-verify=true".split())
            return
    raise KubeContextError(f"No active {kube} context within:\n{c}")

def getMyPublicIp() -> ipaddress.IPv4Address:
    announce("Getting public IP address")
    try:
        i = runCollect("curl ipinfo.io".split())
    except CalledProcessError as e:
        sys.exit("Unable to reach the internet. Are your DNS resolvers set "
                "correctly?")

    try:
        x = json.loads(i)
        myIp = ipaddress.IPv4Address(x["ip"])
        announceBox(f"Your visible IP address is {myIp}. Ingress to your "
                "newly-created bastion server will be limited to this address "
                "exclusively.")
        return myIp
    except ValueError:
        print(f"Unable to retrieve my public IP address; got {i}")
        raise

def getSshPublicKey() -> str:
    announce(f"Retrieving public ssh key {rsaPub}")
    try:
        with open(rsaPub) as rf:
            return rf.read()
    except IOError as e:
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
    ready_pods, all_pods = ready.get_pods(namespace)
    numer = len(ready_pods)
    denom = len(all_pods)
    if mincontainers:
        denom = min(mincontainers, denom)
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

def getStarburstUrl() -> str:
    if tlsenabled():
        scheme = "https"
    else:
        scheme = "http"

    host = starburstfqdn
    port = getLclPort("starburst")

    return f"{scheme}://{host}:{port}"

def getStarburstHttpUrl() -> str:
    return getStarburstUrl() + "/v1/statement"

def loadBalancerResponding(service: str) -> bool:
    assert service in services

    # It is assumed this function will only be called once the ssh tunnels
    # have been established between the localhost and the bastion host
    try:
        if service == "starburst":
            url = getStarburstUrl() + "/ui/login.html"
            r = requests.get(url, verify = tlsenabled(), timeout=1.5)
        elif cachesrv_enabled and service == "cache-service":
            port = getLclPort("cache-service")
            url = f"http://{localhost}:{port}/v1/status"
            r = requests.head(url, timeout=1.5)
        return r.status_code == 200
    except requests.exceptions.ConnectionError as e:
        pass
    except requests.exceptions.Timeout as e:
        pass
    return False

# Get a list of load balancers, in the form of a dictionary mapping service
# names to load balancer hostname or IP address. This function takes a list of
# service names (usually starburst), and returns any load balancers found. The
# list returned might not cover all the services presented, notably in the case
# when the load balancers aren't yet ready. The caller needs to be prepared for
# this possibility.
def getLoadBalancers(services: list, namespace: str) -> dict[str, str]:
    lbs: dict[str, str] = {}
    namesp = f" --namespace {namespace}" if namespace else ""
    for serv in services:
        ingress = None
        if ingresslb and serv == "starburst":
            r = runTry(f"{kube}{namesp} get ing -ojson {ingressname}".split())
            if r.returncode == 0:
                jout = json.loads(r.stdout)
                assert "items" not in jout
                ingress = jout
        r = runTry(f"{kube}{namesp} get svc -ojson {serv}".split())
        if r.returncode == 0:
            jout = json.loads(r.stdout)
            assert "items" not in jout
            s = jout

            # Metadata section
            meta = s["metadata"] # this should always be present
            assert meta["namespace"] == namespace # we only asked for this
            if not "name" in meta:
                continue
            name = meta["name"]
            assert name == serv, f"Unexpected service {name}"
            
            # Status section - now see if its IP is allocated yet
            if not "status" in s:
                continue
            status = s["status"]

            if ingress:
                assert ingresslb and serv == "starburst"
                # Metadata section
                ingmeta = ingress["metadata"] # this should always be present
                assert ingmeta["namespace"] == namespace
                if not "name" in ingmeta:
                    continue
                ingname = ingmeta["name"]
                assert ingname == ingressname, f"Unexpected ingress {ingname}"

                annot = meta['annotations'] # NB: annot from the svc, not ing
                assert "cloud.google.com/neg" in annot
                assert annot["cloud.google.com/neg"] == '{"ingress":true}'

                if not "status" in ingress:
                    continue
                status = ingress["status"] # get status from ing not svc

            if "loadBalancer" not in status:
                continue
            lb = status["loadBalancer"]
            if not "ingress" in lb:
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
    url = "https://{h}:{p}/".format(h = localhost, p = getLclPort("apiserv"))
    try:
        r = requests.get(url, verify = False) # ignore certificate
        # Either forbidden (403), unauthorised (403) or 200 are acceptable
        if r.status_code in (401, 403, 200):
            return 1.0 # all done!
    except requests.exceptions.ConnectionError as e:
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
        self.command = "ssh -N -L{p}:{a}:{k} ubuntu@{b}".format(p = lPort, a =
                rAddr, k = rPort, b = bastionIp)
        print(self.command)
        self.p = subprocess.Popen(self.command.split())
        assert self.p is not None
        announce("Created tunnel " + str(self))

    def __del__(self):
        announce("Terminating tunnel " + str(self))
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

# Input dictionary is the output variables from Terraform.
def establishBastionTunnel(env: dict) -> list[Tunnel]:
    # The new bastion server will have a new host key. Delete the old one we
    # have and grab the new one.
    announce(f"Replacing bastion host keys in {knownhosts}")
    try:
        runStdout("ssh-keygen -q -R {b}".format(b =
            env["bastion_address"]).split())
    except CalledProcessError as e:
        print("Unable to remove host key for {b} in {k}. Is file "
                "missing?".format(b = env["bastion_address"], k = knownhosts))
    cmd = "ssh-keyscan -4 -p22 -H {b}".format(b = env["bastion_address"])
    f = lambda: run(cmd.split(), check = True, verbose = False)
    print(cmd)
    cp = retryRun(f, 3, cmd)
    if cp.returncode != 0:
        sys.exit("Unable, after repeated attempts, to contact new host "
                "{}".format(env["bastion_address"]))
    hostkeys = cp.stdout.strip()
    print("Adding {n} host keys from bastion to {k}".format(n =
        len(hostkeys.splitlines()), k = knownhosts))
    appendToFile(knownhosts, hostkeys)

    tuns = []

    # Start up the tunnel to the Kubernetes API server
    tun = Tunnel("k8s-apiserver", env["bastion_address"],
            getLclPort("apiserv"), env["k8s_api_server"],
            getRmtPort("apiserv"))
    tuns.append(tun)

    # Now that the tunnel is in place, update our kubecfg with the address to
    # the tunnel, keeping everything else in place
    updateKubeConfig()

    # Ensure that we can talk to the api server
    announce("Waiting for api server to respond")
    spinWait(waitUntilApiServerResponding)

    # Start up the tunnel to the LDAP server
    if authnldap:
        assert tlsenabled()
        tun = Tunnel("ldaps", env["bastion_address"], getLclPort("ldaps"),
                ldapfqdn, getRmtPort("ldaps"))
        tuns.append(tun)

    # Copy my private RSA key over to the bastion.
    # FIXME Yes, that is slightly dangerous.
    if upstreamSG:
        announce("Copying over private RSA key to bastion")
        runTry("scp {r} ubuntu@{h}:/home/ubuntu/.ssh/id_rsa".format(r = rsa,
            h = env["bastion_address"]).split())

    return tuns

def ensureClusterIsStarted(skipClusterStart: bool) -> \
        tuple[list[Tunnel], dict]:
    env = {"BastionLaunchScript": bastlaunchf,
           "BucketName":          bucket,
           "CacheServiceEnabled": cachesrv_enabled,
           "CapacityType":        capacityType,
           "ClusterName":         clustname,
           'DisableBastionFw':    nobastionfw,
           "DownstreamSG":        downstreamSG,
           "DbInstanceType":      dbInstanceType,
           "DBName":              dbschema,
           "DBNameCacheSrv":      dbcachesrv,
           "DBNameEventLogger":   dbevtlog,
           "DBNameHms":           dbhms,
           "DBPassword":          dbpwd,
           "DBUser":              dbuser,
           "InstanceTypes":       instanceTypes,
           "LdapLaunchScript":    ldaplaunchf,
           "MaxPodsPerNode":      maxpodpnode,
           "MyCIDR":              mySubnetCidr,
           "MyPublicIP":          getMyPublicIp(),
           'MySqlEnabled':        mysql_enabled,
           'NetwkName':           netwkname,
           "NodeCount":           nodeCount,
           'PostgreSqlEnabled':   postgres_enabled,
           "SmallInstanceType":   smallInstanceType,
           "SshPublicKey":        getSshPublicKey(),
           "Region":              region,
           "Target":              target,
           "UpstrBastion":        upstrBastion,
           "UpstreamSG":          upstreamSG,
           "UserName":            username,
           "LongName":            longname,
           "Zone":                zone}

    assert target in clouds

    if target == "az":
        env["ResourceGroup"] = resourcegrp
        env["StorageAccount"] = storageacct
    elif target == "gcp":
        env["GcpProjectId"] = gcpproject
        env["GcpAccount"] = gcpaccount

    parameteriseTemplate(tfvars, tfdir, env)

    # The terraform run. Perform an init, then an apply.
    if not skipClusterStart:
        announce("Starting terraform run")
        t = time.time()
        runStdout(f"{tf} init -upgrade -input=false".split())
        runStdout(f"{tf} apply -auto-approve -input=false".split())
        announce("terraform run completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

    # Get variables returned from terraform run
    env = get_output_vars()

    # Start up ssh tunnels via the bastion, so we can run kubectl and ldap
    # locally from the workstation
    tuns = establishBastionTunnel(env)

    # Don't continue until all nodes are ready
    announce("Waiting for nodes to come online")
    spinWait(lambda: waitUntilNodesReady(nodeCount))

    # Don't continue until all K8S system pods are ready
    announce("Waiting for K8S system pods to come online")
    spinWait(lambda: waitUntilPodsReady("kube-system"))
    return tuns, env

# Starburst pods sometimes get stuck in Terminating phase after a helm upgrade.
# Kill these off immediately to save time and they will restart quickly.
def killAllTerminatingPods() -> None:
    lines = runCollect(f"{kubens} get pods --no-headers".split()).splitlines()
    for l in lines:
        col = l.split()
        name = col[0]
        status = col[2]
        if status == "Terminating":
            r = runTry(f"{kubens} delete pod {name} --force "
                    "--grace-period=0".split())
            if r.returncode == 0:
                print(f"Terminated pod {name}")

# TODO Azure and GCP allow static IPs to be specified for LBs, so we rely on
# that to set up LDAP during our Terraform run with those IPs. AWS doesn't
# allow IPs to be explicitly set for load balancers, so we have to take a
# different approach post-Terraform, which is to create a CNAME in Route 53
# that references the (classic) LBs that AWS sets up.
def setRoute53Cname(lbs: dict[str, str], route53ZoneId: str,
        delete: bool = False) -> None:
    announce("{v} route53 entries for {s}".format(v = "Deleting" if delete else
        "Creating", s = ", ".join(services)))
    batchf = f"{tmpdir}/crrs_batch.json"
    batch: Dict[str, Any] = {
            "Comment": "DNS CNAME records for starburst.",
            "Changes": []
            }
    action = "DELETE" if delete else "UPSERT"
    for name, host in lbs.items():
        assert name in services

        # If multi-cloud Stargate is enabled, then we want each worker to point
        # to the bastion address, so we can pipe it to the next Starburst
        # instance rather than to itself. We are actually pointing the
        # Starburst FQDN to the bastion FQDN via a CNAME, then the bastion FQDN
        # has an A record that points to the internal bastion IP.
        if upstreamSG and name == "starburst":
            host = bastionfqdn
        
        batch["Changes"].append({
            "Action": action,
            "ResourceRecordSet": {
                "Name": f"{name}.{domain}",
                "Type": "CNAME",
                "TTL": 300,
                "ResourceRecords": [{ "Value": host }]}})
    replaceFile(batchf, json.dumps(batch))
    cmd = "aws route53 change-resource-record-sets --hosted-zone-id " \
            f"{route53ZoneId} --change-batch file://{batchf}"
    runCollect(cmd.split())

def startPortForwardToLBs(bastionIp: str, route53ZoneId: str) -> list[Tunnel]:
    tuns: list[Tunnel] = []

    announce("Waiting for pods to be ready")
    expectedContainers = numberOfContainers(nodeCount)
    spinWait(lambda: waitUntilPodsReady(namespace, expectedContainers))

    announce("Waiting for deployments to be available")
    expectedReplicas = numberOfReplicas(nodeCount)
    spinWait(lambda: waitUntilDeploymentsAvail(namespace, expectedReplicas))

    # now the load balancers need to be running with their IPs assigned
    announce("Waiting for load-balancers to launch")
    spinWait(lambda: waitUntilLoadBalancersUp(services, namespace))

    #
    # Get the DNS name of the load balancers we've created
    #
    lbs = getLoadBalancers(services, namespace)

    # we should have a load balancer for every service we'll forward
    assert len(lbs) == len(services)
    for svc in services:
        assert svc in lbs
        tuns.append(Tunnel(svc, ipaddress.IPv4Address(bastionIp),
            getLclPort(svc), lbs[svc], getRmtPort(svc)))

    # make sure the load balancers are actually responding
    announce("Waiting for load-balancers to start responding")
    spinWait(lambda: waitUntilLoadBalancersUp(services, namespace,
        checkConnectivity = True))

    # TODO AWS Doesn't support specification of a static IP for the ELB, so we
    # cannot set up Route53 in Terraform to point to a static IP. Instead we
    # need to use the aws cli to hand-modify the Route53 entries to create
    # aliases to our load-balancer DNS names.
    if target == "aws":
        assert route53ZoneId
        setRoute53Cname(lbs, route53ZoneId)

    return tuns

def dontLoadCat(cat: str) -> bool:
    avoidcat = {evtlogcat, tpc.tpchcat, tpc.tpcdscat, syscat, sfdccat}

    # Synapse serverless pools are currently read-only so we can't write to
    # them.
    # TODO Synapse node pools and Redshift are writeable but extremely slow. So
    # don't write to them for now. We'll have to do the same with Redshift
    # below too, as it's also painfully slow for writes.
    if target == 'az':
        avoidcat.add(synapseslcat)
        avoidcat.add(synapsenpcat)
    elif target == 'aws':
        avoidcat.add(redshiftcat)

    return cat in avoidcat or cat.startswith("sg_")

    # Synapse node pools are writeable but extremely slow.

def get_sql_command_group() -> SqlCommandGroup:
    conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
    return SqlCommandGroup(conn)

def run_cmds_and_spinwait(scg: SqlCommandGroup, seq: bool = False) -> None:
    # Issue all SQL commands in parallel
    if seq:
        scg.run_commands_seq()
    else:
        scg.run_commands()
    # Progress meter on all SQL commands we've issued
    spinWait(scg.ratio_done)
    scg.wait_until_done() # Should be a no-op

def uniqify(catalog: str, schema: str) -> str:
    global shortname

    uniqschema = schema

    # If we're using the same metastore for multiple catalogs, then we need to
    # distinguish by catalog in the schema name. This is only important for
    # Glue right now, since it shows the catalog as a 'database', and that
    # needs to be unique. Both S3 and Delta use Glue right now.
    if catalog in gluecats:
        uniqschema += '_' + catalog

    # If the catalog is shared by multiple users, and the catalog exposes the
    # schema name to those users, then we then we need to distinguish the
    # schema name by user to avoid potential collisions. This is true for
    # BigQuery, S3 and Delta today.
    if catalog in sharedcats:
        uniqschema += '_' + shortname

    return uniqschema

def uniqify_for_hive(schema: str) -> str:
    return uniqify(hivecat, schema)

def get_matching_bq_schemas(schema_pfx: str) -> list[str]:
    q = f"show schemas in {bqcat} like '{schema_pfx}%'"
    conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
    stab = conn.send_sql(q)
    return [s[0] for s in stab]

# Generate all the commands needed to drop any existing schemas
def get_drop_schema_commands(catalogs: set[str],
                             schemas: set[str]) -> tuple[list[str],
                                                         SqlCommandGroup]:
    drop_schema_names: list[str] = []
    scg = get_sql_command_group()

    for catalog in catalogs:
        for schema in schemas:
            # If the destination schema is used by the cache service for
            # storage, then that can *only* happen for hivecat
            if schema in cachesch and catalog != hivecat:
                continue

            uniq_dst_schema = uniqify(catalog, schema)
            def add_drop_schema_cmd(schema: str) -> None:
                old_fq_schema = f'{catalog}.{schema}'
                drop_schema_names.append(old_fq_schema)
                scg.add_sql_command(f'DROP SCHEMA IF EXISTS {old_fq_schema}')

            # NOTE: BigQuery has an annoying behaviour that it takes several
            # minutes to 'forget' about a schema ('dataset') it says was
            # dropped, and if you re-use the name, it borks. So we make the new
            # schema even "more" unique by adding a random number in the name,
            # which means on cleanup of old schemas, we have to manually look
            # for all the old ones.
            if catalog == bqcat:
                bqschemas = get_matching_bq_schemas(schema_pfx=uniq_dst_schema)
                for bqschema in bqschemas:
                    add_drop_schema_cmd(bqschema)
            else:
                add_drop_schema_cmd(uniq_dst_schema)

    return (drop_schema_names, scg)

# Returns the correctly-casted columns from a source table. This function
# should only be called if the source table has unsupported types.
def get_casted_columns(cg: SqlCommandGroup,
                       type_mappings: list[tuple[str, str]],
                       ct_query: str,
                       src_catalog: str,
                       src_schema: str,
                       src_table: str) -> None:
    mapv = ", ".join(["('{}', '{}')".format(mp[0], mp[1])
                      for mp in type_mappings])

    # Create a set of columns that are either passed-in as normal, or are
    # casted to a new type, where the old type is unsupported on this catalog
    q = ("SELECT COALESCE('CAST (' || c.column_name || ' AS ' || t.y || "
         "') AS ' || c.column_name, c.column_name) "
         "FROM {sc}.information_schema.columns AS c "
         "LEFT JOIN (VALUES {pats}) AS t(x, y) "
         "ON c.data_type LIKE t.x "
         "WHERE c.table_schema = '{ss}' "
         "AND c.table_name = '{st}'".format(sc=src_catalog, ss=src_schema,
                                            st=src_table, pats=mapv))

    # Get all the columns, and return as a list joined with commas, ready to be
    # injected into our CTAS statement
    def cb(ctab: list[list[str]]) -> tuple[str, str]:
        cols = ", ".join([c[0] for c in ctab])
        return (src_table, ct_query.format(cols))

    cg.add_sql_command(q, cb)

# Generate all the commands needed to create all the required new schemas in
# the destination catalog
def get_create_schema_table_commands(dst_catalogs: set[str],
                                     schemas: set[str],
                                     hiveTarget: str,
                                     src_catalog: str,
                                     tpc_cat_info: tpc.TpcCatInfo) -> \
                                             tuple[list[str], list[str],
                                                   SqlCommandGroup,
                                                   SqlCommandGroup]:
    create_schema_names: list[str] = []
    schemas_with_tables: list[str] = []
    scg_sch = get_sql_command_group()
    scg_tab = get_sql_command_group()

    for dst_catalog in dst_catalogs:
        allschemas = schemas

        # NOTE If we are writing to hivecat, then add in the cache schemas
        # automatically here so we create them at the same time
        # FIXME This is a horrible hack. We should hand in the schemas
        # explicitly. Maybe hand in a copy vector that explicitly lists the
        # schemas mapped to the catalogs?
        if dst_catalog == hivecat:
            allschemas |= cachesch

        for schema in allschemas:
            # For cache schemas, only write those to hivecat
            if schema in cachesch and dst_catalog != hivecat:
                continue

            uniq_dst_schema = uniqify(dst_catalog, schema)

            # NOTE: BigQuery has an annoying behaviour that it takes several
            # minutes to 'forget' about a schema ('dataset') it says was
            # dropped, and if you re-use the name, it borks. So we make the new
            # schema even "more" unique by adding a random number in the name,
            # which means on cleanup of old schemas, we have to manually look
            # for all the old ones.
            if dst_catalog == bqcat:
                uniq_dst_schema += '_' + randomString(4)

            schema_pair = [dst_catalog, uniq_dst_schema]

            clause = ""
            if dst_catalog in lakecats:
                new_fq_schema_path = '/'.join([hiveTarget] + schema_pair)
                clause = (f" WITH (LOCATION = '{new_fq_schema_path}')")

            new_fq_schema_name = '.'.join(schema_pair)
            create_schema_names.append(new_fq_schema_name)
            sql_cmd = (f'CREATE SCHEMA IF NOT EXISTS '
                       f'{new_fq_schema_name}{clause}')
            scg_sch.add_sql_command(sql_cmd)

            # For cache schemas, we don't create new tables
            if schema in cachesch:
                continue

            # For anything after this point, we are creating tables
            schemas_with_tables.append(new_fq_schema_name)

            # Determine the name of the uniqified source schema. It might be
            # the base schema name, or might include additional elements to
            # ensure uniqueness across catalogs and users. Also generate the
            # fully qualified version of this unique source schema.
            uniq_src_schema = schema
            if src_catalog == hivecat:
                uniq_src_schema = uniqify(src_catalog, schema)
            src_fq_schema_name = '.'.join([src_catalog, uniq_src_schema])

            global unsupported_types
            type_mappings = unsupported_types.get(dst_catalog)
            scg_cc = get_sql_command_group()
            for src_table in tpc_cat_info.get_table_names():
                sql_cmd = (f'CREATE TABLE IF NOT EXISTS '
                           f'{new_fq_schema_name}.{src_table} '
                           f'AS SELECT {{}} '
                           f'FROM {src_fq_schema_name}.{src_table}')

                if type_mappings:
                    # We need to cast some of the columns. The following
                    # function call will queue for eventual issue a SQL
                    # statement that will prepare the list of arguments with
                    # the appropriate castings.
                    get_casted_columns(scg_cc, type_mappings, sql_cmd,
                                       src_catalog, uniq_src_schema, src_table)
                else:
                    # We don't need to cast, so SELECT * as normal
                    scg_tab.add_sql_command(sql_cmd.format('*'))

            # If we prepared SQL statements to gather the casted columns, then
            # execute those now and collect the results, then put those into
            # our CREATE TABLE command group.
            if type_mappings:
                run_cmds_and_spinwait(scg_cc)
                rs: list[tuple[str, str]] = \
                        scg_cc.wait_and_get_callback_results()
                for src_table, sql_cmd_casted in rs:
                    scg_tab.add_sql_command(sql_cmd_casted)

    return create_schema_names, schemas_with_tables, scg_sch, scg_tab

def get_cache_schema_tables(fq_schema_name: str) -> set[str]:
    try:
        q = f'SHOW TABLES IN {fq_schema_name}'
        conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
        stab = conn.send_sql(q)
        return {s[0] for s in stab}
    except sql.TrinoConnection.ApiError as e:
        # We might get an ApiError because the cache schema doesn't exist. In
        # that case, just return an empty set
        return set()

def get_view_names(catalog: str, schema: str) -> set[str]:
    try:
        q = (f"SELECT table_name FROM {catalog}.information_schema.views "
             f"WHERE table_schema = '{schema}'")
        conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
        stab = conn.send_sql(q)
        return {s[0] for s in stab}
    except sql.TrinoConnection.ApiError as e:
        # We might get an ApiError because the cache schema doesn't exist. In
        # that case, just return an empty set
        return set()

def drop_tables_schemas(env: dict, tpc_cat_info: tpc.TpcCatInfo,
                        catalogs: set[str], schemas: set[str]) -> None:
    drop_schema_names, scg_sch = get_drop_schema_commands(catalogs, schemas)

    # Using the returned schema names, create a list of drop table commands,
    # and queue these in a separate command queue which we'll run first, before
    # we drop the schemas.
    if drop_schema_names:
        scg_tab = get_sql_command_group()

        for fq_schema in drop_schema_names:
            def add_drop_command(obj, fq_schema, table_name):
                def make_dt_cb():
                    scg_tab.add_sql_command(f'DROP {obj} IF EXISTS '
                                            f'{fq_schema}.{table_name}')
                return make_dt_cb

            # If this schema is used for cache storage (table-scan redirection,
            # or materialised views) then we need to get rid of all the tables
            # we find inside it first.
            catalog, schema = tuple(fq_schema.split('.'))
            csmatches = any(map(lambda x: schema.startswith(x), cachesch))

            views = get_view_names(catalog, schema)

            # If this is not a cache schema, then the only tables will be the
            # ones copied over from TPC; so just drop those table names.
            # Otherwise find out the list of tables with a query.
            tables = tpc_cat_info.get_table_names() if not csmatches \
                    else get_cache_schema_tables(fq_schema)
                    
            for table in tables:
                obj = 'TABLE'

                if views and table in views:
                    obj = 'VIEW'
                elif schema.startswith(mvsch):
                    obj = 'MATERIALIZED VIEW'

                add_drop_command(obj, fq_schema, table)()

        s = ', '.join(drop_schema_names)
        announce(f'dropping tables for schemas: {s}')
        run_cmds_and_spinwait(scg_tab)

        announce(f'dropping schemas: {s}')
        run_cmds_and_spinwait(scg_sch)

def copy_schemas_with_tables(env: dict, tpc_cat_info: tpc.TpcCatInfo,
                             srcCatalog: str, srcSchemas: set[str],
                             dstCatalogs: set[str]) -> None:
    # Never write to the source, or to unwritable catalogs
    dstCatalogs = {c for c in dstCatalogs
                   if not dontLoadCat(c) or c == srcCatalog}
    if len(dstCatalogs) < 1:
        return

    hiveTarget = getObjectStoreUrl(env)
    create_schema_names, schemas_with_tables, scg_sch, scg_tab = \
            get_create_schema_table_commands(dstCatalogs, srcSchemas,
                                             hiveTarget, srcCatalog,
                                             tpc_cat_info)

    #
    # create the schemas
    #
    announce('creating schema{s} in {cats}: '
             '{schs}'.format(s = "s" if len(create_schema_names) > 1 else "",
                             schs = ', '.join(create_schema_names),
                             cats = ', '.join(dstCatalogs)))
    run_cmds_and_spinwait(scg_sch)

    #
    # finally, create tables
    #
    announce('creating tables in {}; '
             'schemas: {}'.format(", ".join(dstCatalogs),
                                  ", ".join(schemas_with_tables)))
    run_cmds_and_spinwait(scg_tab)

# Incredibly, Azure doesn't currently provide a simple way of doing an rm -rf
# on a directory. So we'll just move everything we find in the root directory
# to an archive directory.
def azArchiveDirectories(accountName: str, accessKey: str,
                         fsName: str) -> None:
    opt = f"--account-name {accountName} --account-key {accessKey} " \
            f"--file-system {fsName} --output json"

    # Get a list of the files we've got
    files = json.loads(runCollect(f"az storage fs file list {opt} "
        "--recursive false --path /".split()))
    if not files:
        return

    announce(f"Archiving all files in {fsName}")
    archivedir = f"archive-" + randomString(8)
    runCollect(f"az storage fs directory create {opt} "
            f"--name {archivedir}".split())

    # Move the files into the archive directory
    for f in files:
        path = f["name"]
        newpath = f"{fsName}/{archivedir}/{path}"
        runCollect(f"az storage fs file move {opt} --path {path} "
                f"--new-path {newpath}".split())
        print(f"Archived {path} to {newpath}")

def eraseBucketContents(env: dict) -> None:
    # Delete everything in the bucket
    assert target in clouds

    # Azure is a special case because it has no way of recursively deleting
    # files and directories, so we'll handle it first.
    if target == "az":
        azArchiveDirectories(storageacct, env["adls_access_key"],
                env["adls_fs_name"])
        return

    if target == "aws":
        cmd = "aws s3 rm s3://{b}/ --recursive".format(b = bucket)
    else:
        assert target == "gcp"
        cmd = "gsutil rm -rf {b}/*".format(b = env["object_address"])

    announce(f"Deleting contents of bucket {bucket}")
    try:
        runStdout(cmd.split())
    except CalledProcessError as e:
        print(f"Unable to erase bucket {bucket} (already empty?)")

def getCatalogs() -> set[str]:
    conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
    ctab = conn.send_sql("show catalogs")
    allcat = {c[0] for c in ctab if not dontLoadCat(c[0])}
    return allcat

def getSchemasInCatalog(catalog: str) -> list[str]:
    conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
    stab = conn.send_sql(f"show schemas in {catalog}")
    return [s[0] for s in stab]

def getTablesForSchemaCatalog(schema: str, catalog: str) -> list[str]:
    conn = sql.TrinoConnection(getStarburstHttpUrl(), trinouser, trinopass)
    ttab = conn.send_sql(f"show tables in {schema}.{catalog}")
    return [t[0] for t in ttab]

def loadDatabases(env: dict, perftest: bool, tpcds_cat_info: tpc.TpcCatInfo,
                  drop_first: bool) -> None:
    # First copy tpcds large scale set to hive...
    scale_sets = {tpcdsbigsch}
    if perftest:
        scale_sets = tpc.scale_sets.range(tpc.scale_sets.smallest(),
                tpc.scale_sets.largest())

    dst_catalogs = getCatalogs()

    if drop_first:
        drop_tables_schemas(env, tpcds_cat_info, dst_catalogs,
                            scale_sets|{tpcdssmlsch}|cachesch - tsrsch)
        # Don't erase bucket after dropping tables, as we want to preserve the
        # tables stored for table scan redirection.

    # Copy from the TPC-DS catalog to Hive.
    copy_schemas_with_tables(env, tpcds_cat_info, tpc.tpcdscat, scale_sets,
                             {hivecat})

    assert hivecat in dst_catalogs
    dst_catalogs.remove(hivecat) # already done hivecat

    if tpcdsbigsch != tpcdssmlsch:
        # Where we have a large schema in Hive, we'll copy from TPC-DS directly
        # to all the other catalogs as they would be too slow to take the
        # larger scale sets
        copy_schemas_with_tables(env, tpcds_cat_info, tpc.tpcdscat,
                                 {tpcdssmlsch}, dst_catalogs)
    else:
        # Where we have a small schema in Hive, we'll copy from Hive (which
        # we've already populated) to all the other catalogs since it's more
        # efficient than re-generating the TPC-H/DS data
        copy_schemas_with_tables(env, tpcds_cat_info, hivecat,
                                 {tpcdssmlsch}, dst_catalogs)

def installSecrets(secrets: dict[str, dict[str, str]]) -> dict[str, str]:
    env = {}
    groups: dict[str, dict[str, str]] = {}
    announce(f"Installing secrets")
    installed = []
    if secrets:
        installed = runCollect(f"{kubens} get secrets "
                f"-o=jsonpath={{.items[*].metadata.name}}".split()).split()

    for name, values in secrets.items():
        # These are needed only for LDAP
        if not authnldap and name == 'ldaptls':
            continue

        # These are needed only for GCP
        if target != "gcp" and name == "gcskey":
            continue

        # We always want to store the secret name, no matter what
        env[name] = name

        # if this isn't a cert group, then record the base filename and fully
        # qualified filename to the environment dict
        if not "isgroup" in values or not values["isgroup"]:
            env[name + "bf"] = values["bf"]
            env[name + "f"] = values["f"]

        # if the secret with that name doesn't yet exist, create it
        if name not in installed:
            # If this isn't a cert group, then install the secret normally. If
            # this is a cert group, and we are terminating TLS at an
            # ingress-based LB, then we need to install a secret that we'll use
            # in the helm chart with the LB.
            if not "isgroup" in values or not values["isgroup"]:
                runStdout("{k} create secret generic {n} --from-file "
                        "{f}".format(k = kubens, n = name, f =
                            values["f"]).split())

    return env

def helmTry(cmd: str) -> subprocess.CompletedProcess:
    return runTry(["helm"] + cmd.split())

def helm(cmd: str) -> None:
    runStdout(["helm"] + cmd.split())

def helmGet(cmd: str) -> str:
    return runCollect(["helm"] + cmd.split())

def ensureHelmRepoSetUp(repo: str) -> None:
    if (r := helmTry("version")).returncode != 0:
        sys.exit("Unable to run helm. Is it installed? Failing out.")

    # There is a bug in helm repo list, wherein it inconsistently returns
    # nonzero error codes when there are no repos installed. So just try to
    # fast-path the common case where the repo is already installed, and
    # otherwise try to install.
    if (r := helmTry("repo list -o=json")).returncode == 0:
        repos = [x["name"] for x in json.loads(r.stdout)]
        if repo in repos:
            announce(f"Upgrading repo {repo}")
            # Unfortunately, helm repo update returns a 0 error code even when
            # it fails. So we actually have to collect the output and look to
            # see if it failed. :-( If it fails, then just remove the repo and
            # re-install it.
            output = helmGet("repo update --fail-on-repo-update-fail")
            if "Update Complete. ⎈Happy Helming!⎈" in output:
                print("Upgrade of repo succeeded")
                return

            announce(f"Update of repo failed. Removing repo {repo}")
            helm(f"repo remove {repo}")

    helm(f"repo add --username {repouser} --password {repopass} {repo} "
         f"{repoloc}")

def helmGetNamespaces() -> list:
    n = []
    try:
        nsl = json.loads(runCollect(f"{kube} get namespaces "
            "--output=json".split()))["items"]
        n = [x["metadata"]["name"] for x in nsl]
    except CalledProcessError as e:
        print("No namespaces found.")

    return n

def helmCreateNamespace() -> None:
    if namespace not in helmGetNamespaces():
        runStdout(f"{kube} create namespace {namespace}".split())
    runStdout(f"{kube} config set-context --namespace=starburst "
            "--current".split())

def helmDeleteNamespace() -> None:
    if namespace in helmGetNamespaces():
        announce(f"Deleting namespace {namespace}")
        runStdout(f"{kube} delete namespace {namespace}".split())
    runStdout(f"{kube} config set-context --namespace=default "
            "--current".split())

def helmGetReleases() -> dict:
    rls = {}
    try:
        rlsj = json.loads(helmGet(f"{helmns} list -ojson"))
        rls = { r["name"]: r["chart"] for r in rlsj }
    except CalledProcessError as e:
        print("No helm releases found.")
    return rls

def helmWhichChartInstalled(module: str) -> Optional[str]:
    chart = None
    release = releases[module] # Get release name for module name
    installed = helmGetReleases()
    if release in installed:
        chart = installed[release] # Get chart for release
    return chart

# Returns a bool indicating if the hive postgres database might have been
# created--either during an install, or because we revved up a version
def helmInstallRelease(module: str, env: dict = {}) -> None:
    env |= {'AuthNLdap':           authnldap,
            "BucketName":          bucket,
            "CacheMvSchema":       uniqify_for_hive(cachemvsch),
            "CacheServiceEnabled": cachesrv_enabled,
            "CacheTsrSchema":      uniqify_for_hive(cachetsrsch),
            "DBName":              dbschema,
            "DBNameEventLogger":   dbevtlog,
            "DBNameCacheSrv":      dbcachesrv,
            "DBNameHms":           dbhms,
            "DBPassword":          dbpwd,
            "EvtLogCat":           evtlogcat,
            'HelmRegistry':        helmregistry,
            'HelmRepoUser':        repouser,
            'HelmRepoPassword':    repopass,
            "HiveCat":             hivecat,
            'IngressLoadBalancer': ingresslb,
            "IngressName":         ingressname,
            "KeystorePass":        keystorepass,
            'MvSchema':            uniqify_for_hive(mvsch),
            'PerformanceTesting':  perftest,
            "RedshiftCat":         redshiftcat,
            "Region":              region,
            'SalesforceEnabled':   sfdcenabled,
            "StarburstHost":       starburstfqdn,
            "StorageAccount":      storageacct,
            "SynapseSlCat":        synapseslcat,
            "SynapseNpCat":        synapsenpcat,
            "Target":              target,
            "TlsEnabled":          tlsenabled(),
            "TrinoUser":           trinouser,
            "TrinoPass":           trinopass,
            "UpstreamSG":          upstreamSG,
            "postgres_port":       dbports["postgres"],
            "Zone":                zone}

    if mysql_enabled:
        env['mysql_port'] = dbports['mysql']

    if target == "gcp":
        env["GcpProjectId"] = gcpproject

    if authnldap:
        env["LdapUri"] = "ldaps://{h}:{p}".format(h = ldapfqdn, p =
                getRmtPort("ldaps"))

    if sfdcenabled:
        env |= {'SfdcCat': sfdccat,
                'SalesforceUser': sfdcuser,
                'SalesforcePassword': sfdcpass,
                'SalesforceSecurityToken': sfdctoken}
                
    if upstreamSG:
        env['UpstreamSG'] = upstreamSG
        env["BastionAzPort"] = getLclPortSG("starburst", "az")
        env["BastionGcpPort"] = getLclPortSG("starburst", "gcp")

    # Parameterise the yaml file that configures the helm chart install. The
    # function returns a tuple, indicating whether the helm chart values file
    # changed, and the location of that same (parameterised) values file.
    changed, yamltmp = parameteriseTemplate(templates[module], tmpdir, env)

    chart = helmWhichChartInstalled(module)
    newchart = charts[module] + "-" + chartversion # which one to install?
    
    if chart == None: # Nothing installed yet, so we need to install
        announce("Installing chart {c} as {r}".format(c = newchart, r =
            releases[module]))
        helm("{h} install {r} {w}/{c} -f {y} --version {v}".format(h = helmns,
            r = releases[module], w = repo, c = charts[module], y =
            yamltmp, v = chartversion))
    # If either the chart values file changed, or we need to update to a
    # different version of the chart, then we have to upgrade
    elif changed or chart != newchart:
        astr = "Upgrading release {}".format(releases[module])
        if chart != newchart:
            astr += ": {oc} -> {nc}".format(oc = chart, nc = newchart)
        announce(astr)
        helm("{h} upgrade {r} {w}/{c} -f {y} --version {v}".format(h = helmns,
            r = releases[module], w = repo, c = charts[module], y =
            yamltmp, v = chartversion))
    else:
        print(f"{chart} values unchanged ➼ avoiding helm upgrade")

def helmUninstallRelease(release: str) -> None:
    helm(f"{helmns} uninstall {release}")

def helmInstallAll(env):
    helmCreateNamespace()
    env |= installSecrets(secrets)
    ensureHelmRepoSetUp(repo)
    # for AWS we use Glue, not a separate HMS
    env |= planWorkerSize(namespace, cachesrv_enabled,
            hms_enabled=(target!='aws'))
    for module in modules:
        helmInstallRelease(module, env)
    # Speed up the deployment of the updated pods by killing the old ones
    killAllTerminatingPods()

def deleteAllServices() -> dict[str, str]:
    # Explicitly deleting services gets rid of load balancers, which eliminates
    # a race condition that Terraform is susceptible to, where the ELBs created
    # by the load balancers endure while the cluster is destroyed, stranding
    # the ENIs and preventing the deletion of the associated subnets
    # https://github.com/kubernetes/kubernetes/issues/93390
    announce("Deleting all k8s services")
    print("Deleting ingresses...")
    runStdout(f"{kubens} delete ingress --all".split())
    lbs = getLoadBalancers(services, namespace)
    if len(lbs) == 0:
        print("No LBs running.")
    else:
        print("Load balancers before attempt to delete services: " + ", ".join(lbs.keys()))
    runStdout(f"{kubens} delete svc --all".split())
    lbs_after = getLoadBalancers(services, namespace)
    if len(lbs_after) == 0:
        print("No load balancers running after service delete.")
    else:
        print("# WARN Load balancers running after service delete! " +
                str(lbs_after))
        print("# WARN This may cause dependency problems later!")
    return lbs

def helmUninstallAll():
    for release, chart in helmGetReleases().items():
        try:
            announce(f"Uninstalling chart {chart}")
            helmUninstallRelease(release)
        except CalledProcessError as e:
            print(f"Unable to uninstall release {release}: {e}")
    killAllTerminatingPods()
    helmDeleteNamespace()

def announceReady(bastionIp: str) -> list[str]:
    a = [getStarburstUrl()]
    who = f"user: {trinouser}"
    if tlsenabled():
        who += f" pwd: {trinopass}"
    a.append(who)
    if downstreamSG:
        a.append(f"downstream bastion: {bastionIp}")
        a.append(f"Allowing ingress from upstream bastion: {upstrBastion}")
    elif upstreamSG:
        a.append(f"upstream bastion: {bastionIp}")
    else:
        a.append(f"bastion: {bastionIp}")
    return a

def getObjectStoreUrl(env: dict) -> str:
    if target == "aws":
        return f"s3://{bucket}" # replace completely
    elif target == "az":
        return "abfs://{f}@{h}".format(f = env["adls_fs_name"], h =
                env["object_address"]) # use the URL for ADLS
    else: # target == "gcp"
        return env["object_address"] # change nothing

def svcStart(perftest: bool, credobj: Optional[creds.Creds] = None,
        skipClusterStart: bool = False, drop_first: bool = False,
        dontLoad: bool = False, nobastionfw: bool = False) -> tuple[list[Tunnel],
                list[str]]:
    # First see if there isn't a cluster created yet, and create the
    # cluster. This will create the control plane and workers.
    tuns: list[Tunnel] = []
    tuns, env = ensureClusterIsStarted(skipClusterStart)

    zid = env["route53_zone_id"] if target == "aws" else None
    env["Region"] = region
    if credobj and isinstance(credobj, creds.Creds):
        env |= credobj.toDict()
    helmInstallAll(env)
    tuns.extend(startPortForwardToLBs(env["bastion_address"], zid))

    tpcds_scale_sets: set[str] = {tpcdssmlsch, tpcdsbigsch}
    tpch_scale_sets = tpcds_scale_sets
    if perftest:
        tpcds_scale_sets = tpc.scale_sets.range(tpcdssmlsch, tpcdsbigsch)

    tpcds_cat_info = tpc.TpcCatInfo(sql.TrinoConnection(getStarburstHttpUrl(),
            trinouser, trinopass), tpc.tpcdscat, tpcds_scale_sets)

    if not dontLoad:
        loadDatabases(env, perftest, tpcds_cat_info, drop_first)

    return tuns, announceReady(env["bastion_address"])

def isTerraformSettled() -> bool:
    r = runTry(f"{tf} plan -input=false "
               "-detailed-exitcode".split()).returncode
    return r == 0

def svcStop(perf_test: bool, onlyEmptyNodes: bool = False) -> None:
    # Re-establish the tunnel with the bastion, or our helm and kubectl
    # commands won't work.
    announce("Checking current Terraform status")

    if isTerraformSettled():
        announce("Re-establishing bastion tunnel")
        env = get_output_vars()
        try:
            tuns = []
            tuns.extend(establishBastionTunnel(env))
            t = time.time()
            zid = env["route53_zone_id"] if target == "aws" else None
            tuns.extend(startPortForwardToLBs(env["bastion_address"], zid))
            scale_sets: set[str] = {tpcdssmlsch, tpcdsbigsch}
            if perf_test:
                scale_sets = tpc.scale_sets.range(tpc.scale_sets.smallest(),
                                                  tpc.scale_sets.largest())
            tpc_cat_info = \
                    tpc.TpcCatInfo(sql.TrinoConnection(getStarburstHttpUrl(),
                                                       trinouser, trinopass),
                                   tpc.tpcdscat, scale_sets)
            drop_tables_schemas(env, tpc_cat_info, getCatalogs(),
                                scale_sets|cachesch)
            eraseBucketContents(env)
            lbs = deleteAllServices()
            # TODO AWS has to be handled differently because of its inability
            # to support specification of static IPs for load balancers.
            if target == "aws" and len(lbs) > 0:
                assert len(lbs) == len(services)
                setRoute53Cname(lbs, env["route53_zone_id"], delete = True)
            helmUninstallAll()
            announce("nodes emptied in " + time.strftime("%Hh%Mm%Ss",
                time.gmtime(time.time() - t)))
        except CalledProcessError as e:
            announceBox(textwrap.dedent("""\
                    Your Terraform is set up, but your bastion host is not
                    responding. It might be a network issue, or it might be
                    your public IP address has changed since you set up. I will
                    try to destroy your terraform without unloading your pods
                    but you might have trouble on the destroy."""))

    if not onlyEmptyNodes:
        announce(f"Ensuring cluster {clustname} is deleted")
        t = time.time()
        runStdout(f"{tf} destroy -auto-approve".split())
        announce("tf destroy completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

def fqdnToDc(fqdn: str) -> str:
    dcs = fqdn.split('.')
    return ",".join([f"dc={d}" for d in dcs])

def getOverlays() -> str:
    return textwrap.dedent("""\
            dn: cn=module,cn=config
            cn: module
            objectClass: olcModuleList
            olcModuleLoad: memberof
            olcModulePath: /usr/lib/ldap
            
            dn: olcOverlay={0}memberof,olcDatabase={1}mdb,cn=config
            objectClass: olcConfig
            objectClass: olcMemberOf
            objectClass: olcOverlayConfig
            objectClass: top
            olcOverlay: memberof
            olcMemberOfRefint: TRUE
            olcMemberOfGroupOC: groupOfNames\n\n""")

def getOu(outype: str, dcs: str) -> str:
    return textwrap.dedent(f"""\
            dn: ou={outype},{dcs}
            objectClass: organizationalUnit
            ou: {outype}\n\n""")

def getUser(user: str, uid: int, gid: int, dcs: str) -> str:
    fn = user.capitalize()
    ln = user[::-1].capitalize()
    return textwrap.dedent(f"""\
            dn: uid={user},ou=People,{dcs}
            objectClass: inetOrgPerson
            objectClass: posixAccount
            objectClass: shadowAccount
            uid: {user}
            sn: {ln}
            givenName: {fn}
            cn: {fn} {ln}
            displayName: {fn} {ln}
            uidNumber: {uid}
            gidNumber: {gid}
            userPassword: {trinopass}
            gecos: {fn} {ln}
            loginShell: /bin/bash
            homeDirectory: /home/{user}\n\n""")

def getGroup(name: str, gidNum: int, dcs: str, members: list[str]) -> str:
    memberstr = "\n".join([f"member: uid={m},ou=People,{dcs}"
        for m in members])
    s = textwrap.dedent(f"""\
            dn: cn={name},ou=Groups,{dcs}
            objectClass: groupOfNames
            cn: {name}\n""")
    s += f"{memberstr}\n\n"
    return s

def buildLdapLauncher(fqdn: str) -> None:
    dcs = fqdnToDc(fqdn)
    certdir = '/etc/ldap/sasl2'
    cacertbf = "cacert.pem"
    ldapkeybf = "ldap.key"
    ldapcertbf = "ldap.pem"
    certinfobf = "certinfo.ldif"
    check_rc=('RC=$?; if [[ $RC -ne 0 ]]; '
            'then echo Command failed with RC=$RC; fi\n')
    check_dns = f'dig {ldapfqdn}\n'

    with open(ldapsetupf) as sh, \
            open(ldaplaunchf, 'w') as wh, \
            open(secrets["ldaptls"]["chain"]) as cach, \
            open(secrets["ldaptls"]["cert"]) as ch, \
            open(secrets["ldaptls"]["key"]) as kh:
        # Copy in the script that installs slapd
        for line in sh:
            wh.write(line)

        # Now add to the script some other commands. First, we want to turn on
        # LDAPS. Write our server cert and our private key to /etc/ldap and
        # permission them appropriately.
        wh.write(f"cat <<EOM | sudo tee {certdir}/{cacertbf}\n")
        for line in cach:
            wh.write(line)
        wh.write("EOM\n")
        wh.write(f"cat <<EOM | sudo tee {certdir}/{ldapkeybf}\n")
        for line in kh:
            wh.write(line)
        wh.write("EOM\n")
        wh.write(f"cat <<EOM | sudo tee {certdir}/{ldapcertbf}\n")
        for line in ch:
            wh.write(line)
        wh.write("EOM\n")

        wh.write("sudo chown -R openldap /etc/ldap\n")
        wh.write("sudo chgrp -R openldap /etc/ldap\n")
        wh.write(f"sudo chmod 0600 {certdir}/*\n")

        # Now add the server cert and private key to slapd.
        wh.write(f"cat <<EOM | sudo tee /tmp/{certinfobf}\n")
        wh.write("dn: cn=config\n")
        wh.write("changetype: modify\n")
        wh.write("replace: olcTLSCACertificateFile\n")
        wh.write(f"olcTLSCACertificateFile: {certdir}/{cacertbf}\n-\n")
        wh.write("replace: olcTLSCertificateKeyFile\n")
        wh.write(f"olcTLSCertificateKeyFile: {certdir}/{ldapkeybf}\n-\n")
        wh.write("replace: olcTLSCertificateFile\n")
        wh.write(f"olcTLSCertificateFile: {certdir}/{ldapcertbf}\n")
        wh.write("EOM\n")
        wh.write(check_dns)
        wh.write("sudo ldapmodify -Y EXTERNAL -H ldapi:// -f "
                f"/tmp/{certinfobf}\n")
        wh.write(check_rc)

        # Enable ldaps
        regex = r"s/(^\s*[^#].*)ldap:/\1ldaps:/g"
        wh.write(f"sudo sed -E -i '{regex}' /etc/default/slapd\n")
        wh.write("sudo systemctl restart slapd\n")
        wh.write(check_rc)

        # Configure for LDAP clients
        wh.write("cat <<EOM | sudo tee /etc/ldap/ldap.conf\n")
        wh.write(f"URI ldaps://{ldapfqdn}:636\n")
        wh.write("TLS_CACERT /etc/ssl/certs/ca-certificates.crt\n")
        wh.write("EOM\n")

        # Enable the memberof plugin
        wh.write("cat <<EOM | sudo tee /tmp/memberof.ldif\n")
        wh.write(getOverlays())
        wh.write("EOM\n")
        wh.write(check_dns)
        wh.write("sudo ldapadd -H ldapi:// -Y EXTERNAL -D 'cn=config' -f "
                "/tmp/memberof.ldif\n")
        wh.write(check_rc)

        # Populate the slapd database with some basic entries that we'll need.
        wh.write("cat <<EOM | sudo tee /tmp/who.ldif\n")
        wh.write(getOu("People", dcs))
        wh.write(getOu("Groups", dcs))
        wh.write(getUser("alice",   10000, 5000, dcs))
        wh.write(getUser("bob",     10001, 5000, dcs))
        wh.write(getUser("carol",   10002, 5001, dcs))
        wh.write(getUser(trinouser, 10100, 5001, dcs))
        wh.write(getGroup("analysts",   5000, dcs, ["alice", "bob"]))
        wh.write(getGroup("superusers", 5001, dcs, ["carol", trinouser]))
        wh.write("EOM\n")
        wh.write(check_dns)
        wh.write("sudo ldapadd -x -w admin -D "
                "cn=admin,dc=az,dc=starburstdata,dc=net -f /tmp/who.ldif\n")
        wh.write(check_rc)
        wh.write("echo finished | sudo tee /tmp/finished\n")

def buildBastionLauncher() -> None:
    with open(bastlaunchf, 'w') as wh:
        wh.write("#!/bin/bash\n\n")
        if upstreamSG:
            wh.write("mkdir -p ~/.ssh\n")
            wh.write("chmod 700 /root/.ssh\n")
            wh.write(f"touch /root/.ssh/known_hosts\n")
            def emitSshTunnel(wh, bindaddr: ipaddress.IPv4Address, lclport:
                    int, rmtIpAddr: ipaddress.IPv4Address, rmtport: int,
                    dnstrmBast: ipaddress.IPv4Address):
                wh.write(f"ssh-keygen -R {dnstrmBast}\n")
                wh.write(f"ssh-keyscan -4 -p22 -H {dnstrmBast} >> "
                        f"/root/.ssh/known_hosts\n")
                wh.write("ssh -n -L "
                        f"{bindaddr}:{lclport}:{rmtIpAddr}:{rmtport} -N "
                        f"ubuntu@{dnstrmBast} &\n")
            starport = getRmtPort("starburst")
            bindaddr = ipaddress.IPv4Address("0.0.0.0")
            if azaddrs:
                lclport = getLclPortSG("starburst", "az")
                rmtaddr = azaddrs["starburst"]
                dnstrmBast = azaddrs["bastion"]
                emitSshTunnel(wh, bindaddr, lclport, rmtaddr, starport,
                        dnstrmBast)
            if gcpaddrs:
                lclport = getLclPortSG("starburst", "gcp")
                rmtaddr = gcpaddrs["starburst"]
                dnstrmBast = gcpaddrs["bastion"]
                emitSshTunnel(wh, bindaddr, lclport, rmtaddr, starport,
                        dnstrmBast)

        wh.write("echo finished > /tmp/finished\n")

def getCloudSummary() -> List[str]:
    if target == "aws":
        cloud = "Amazon Web Services"
    elif target == "az":
        cloud = "Microsoft Azure"
    else:
        cloud = "Google Cloud Services"
    if len(instanceTypes) > 1:
        itype = "[SPOT like {}, {}, &c]".format(instanceTypes[0],
                instanceTypes[1])
    else:
        itype = instanceTypes[0]
    return [f"Cloud: {cloud}",
        f"Region: {region}",
        # FIXME this should show the instance type actually selected!
        f"Cluster: {nodeCount} × {itype}"]

def getSecrets() -> None:
    try:
        with open(secretsf) as fh:
            s = yaml.load(fh, Loader = yaml.FullLoader)
    except IOError as e:
        sys.exit(f"Couldn't read secrets file {secretsf}")

    groups: dict[str, dict[str, Any]] = {}

    for name, values in s.items():
        base = values["bf"]
        if "dir" in values:
            base = values["dir"] + "/" + base
        filename = bbio.where(base)

        # If the secret is not generated later by this program, then it is
        # a pre-made secret, and it must already be on disk and readable.
        if ("generated" not in values or values["generated"] == False) \
                and not bbio.readableFile(filename):
            sys.exit(f"Can't find a readable file at {filename} for {name}")

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
            except CalledProcessError as e:
                print("Unable to verify cert {c} & chain {ch}".format(c =
                    values["cert"], ch = values["chain"]))
                sys.exit(-1)
        secrets[groupname] = values

def announceSummary() -> None:
    announceLoud(getCloudSummary())

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
    # We now always require a hosts entry for the starburst host into
    # /etc/hosts, invariantly mapping to 127.0.0.1 (localhost).
    announce(f'Ensuring needed mapping entries are in {hostsf}')

    # Start by trying to see if the entries are already in the hosts file, in
    # the form we want. If they are, we don't need to create them.
    if bbio.readableFile(hostsf):
        with open(hostsf) as fh:
            for line in fh:
                # skip commented lines
                if re.match(r"^\s*#", line):
                    continue

                # skip non-mapping entries
                cols = line.split()
                if len(cols) < 2:
                    continue

                # this is a mapping entry; see if we find a mapping that
                # matches what we're looking for
                ip = cols[0]
                hostname = cols[1]
                if ip == localhostip and hostname == starburstfqdn:
                    # Success! We have all we need in the /etc/hosts file, so
                    # we can quit searching and leave this function
                    print(f'Found {hostsf} entry satisfying requirement:')
                    print(line.strip())
                    return

    # We didn't manage to return out of this function, so the /etc/hosts file
    # didn't have the required entries. Offer to create them.
    print(f'You will need {starburstfqdn} in {hostsf}.')
    print(f'I can add this but will need to run this as sudo:')
    cmd = f"echo {localhostip} {starburstfqdn} | sudo tee -a {hostsf}"
    print(cmd)
    yn = input("Would you like me to run that with sudo? [y/N] -> ")
    if yn.lower() in ("y", "yes"):
        rc = runShell(cmd)
        if rc == 0:
            print(f"Added {starburstfqdn} to {hostsf}.")
            return
        else:
            print(f"Unable to write to {hostsf}. Try yourself?")
    sys.exit(f"Script cannot continue without {starburstfqdn} in {hostsf}")

def cleanOldTunnels() -> None:
    # Check to see if anything looks suspiciously like an old ssh tunnel, and
    # see if the user is happy to kill them.
    announce('Looking for old tunnels to clean')
    r = re.compile(r'ssh -N -L.+:.+:.+ ubuntu@')
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
    count = 0.0
    waits = []
    for i in range(random.randrange(5, 21)):
        waits.append(random.randrange(1, 11))
    announceBox(f'Waits are {waits}')
    cg = CommandGroup()
    for w in waits:
        def make_cb(w: int) -> Callable[[], None]:
            def sleep_x() -> None:
                time.sleep(float(w))
            return sleep_x
        cg.add_command(make_cb(w), w)
    cg.run_commands()
    spinWait(cg.ratio_done)
    cg.wait_until_done()
    
def main() -> None:
    if ns.progmeter_test:
        spinWaitCGTest()
        sys.exit(0)
    elif ns.node_layout:
        planWorkerSize(namespace, cachesrv_enabled,
                hms_enabled=(target!='aws'), verbose=True)
        sys.exit(0)

    announce("Verifying environment")
    getSecrets()
    announceSummary()
    credobj = creds.getCreds(target)
    checkRSAKey()
    checkEtcHosts()
    cleanOldTunnels()
    buildLdapLauncher(domain)
    buildBastionLauncher()
    if target == "gcp":
        announce(f"GCP project is {gcpproject}")
    if nobastionfw:
        announceBox("Bastion firewall will be disabled!")
    print(f"Your CIDR is {mySubnetCidr}")

    w: list[str] = []
    started = False

    if ns.command in ("stop", "restart"):
        svcStop(perftest, ns.empty_nodes)

    tuns: list[Tunnel] = []
    if ns.command in ("start", "restart"):
        newtuns, w = svcStart(perftest, credobj, ns.skip_cluster_start,
                ns.drop_tables, ns.dont_load, nobastionfw)
        tuns.extend(newtuns)
        started = True
        announceBox(f"Your {rsaPub} public key has been installed into the "
                "bastion server, so you can ssh there now (user 'ubuntu').")

    if ns.command == "status":
        announce("Fetching current status")
        started = isTerraformSettled()
        if started:
            env = get_output_vars()
            w = announceReady(env["bastion_address"])

    y = getCloudSummary() + ["Service is " + ("started on:" if started else
        "stopped")]
    if len(w) > 0:
        y += w

    if ns.command in ("start", "restart") and started:
        y.append("Connect now to localhost ports:")
        y += [str(i) for i in tuns]
        announceLoud(y)
        input("Press return key to quit and terminate tunnels!")
    else:
        announceLoud(y)

main()
