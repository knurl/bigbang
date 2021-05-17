#!python

import os, hashlib, argparse, sys, pdb, textwrap, requests, json, yaml, re
import subprocess, ipaddress, glob, threading, time, concurrent.futures, jinja2
import atexit, psutil # type: ignore
from run import run, runShell, runTry, runStdout, runCollect
from subprocess import CalledProcessError
from typing import List, Tuple, Iterable, Callable, Optional, Any
from urllib.parse import urlparse

# Do this just to get rid of the warning when we try to read from the
# api server, and the certificate isn't trusted
from urllib3 import disable_warnings, exceptions # type: ignore
disable_warnings(exceptions.InsecureRequestWarning)

def myDir():
    return os.path.dirname(os.path.abspath(__file__))
def where(leaf):
    return os.path.join(myDir(), leaf)
def readableFile(p):
    return os.path.isfile(p) and os.access(p, os.R_OK)
def readableDir(p):
    return os.path.isdir(p) and os.access(p, os.R_OK | os.X_OK)
def writeableDir(p):
    return readableDir and os.access(p, os.W_OK)

#
# Global variables.
#
clouds         = ("aws", "az", "gcp")
templatedir    = where("templates")
tmpdir         = "/tmp"
rsa            = os.path.expanduser("~/.ssh/id_rsa")
rsaPub         = os.path.expanduser("~/.ssh/id_rsa.pub")
knownhosts     = os.path.expanduser("~/.ssh/known_hosts")
tfvars         = "variables.tf" # basename only, no path!
awsauthcm      = "aws-auth-cm.yaml" # basename only, no path!
dbports        = { "mysql": 3306, "postgres": 5432 }
tpchschema     = "tiny"
gcskeyname     = "gcs-keyfile"
gcskeyfbn      = f"key.json"
tpchcat        = "tpch"
hivecat        = "hive"
syscat         = "system"
evtlogcat      = "postgresqlel"
bqcat          = "bigquery" # for now, connector doesn't support INSERT or CTAS
remote_cats    = ["remote_hive", "remote_postgresql", "remote_mysql"]
avoidcat       = [tpchcat, syscat, evtlogcat, bqcat] + remote_cats
trinouser      = "presto_service"
trinopass      = "test"
dbschema       = "fdd"
dbevtlog       = "evtlog" # event logger PostgreSQL instance
dbuser         = "fdd"
dbpwd          = "a029fjg!>dfgBiO8"
namespace      = "starburst"
helmns         = f"-n {namespace}"
kube           = "kubectl"
kubecfgf       = os.path.expanduser("~/.kube/config")
kubens         = f"{kube} -n {namespace}"
minnodes       = 2
maxpodpnode    = 16
toreap         = [] # Accumulate tunnels to destroy
awsdir         = os.path.expanduser("~/.aws")
awsconfig      = os.path.expanduser("~/.aws/config")
awscreds       = os.path.expanduser("~/.aws/credentials")
thishost       = "localhost"
prestohost     = "presto.az.starburstdata.net"
sharedsecbf    = "sharedsecret"
sharedsecf     = where(sharedsecbf)
keystorebf     = "presto.pkcs12"
keystoref      = where(keystorebf)
patchfilebf    = "starburst-enterprise.diff"
patchfile      = where(patchfilebf)

#
# Start of execution. Handle commandline args.
#

p = argparse.ArgumentParser(description=
        f"""Create your own Starbust demo service in AWS, Azure or GCP,
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
p.add_argument('-t', '--target', action="store",
        help="Force cloud target to specified value.")
p.add_argument('-z', '--zone', action="store",
        help="Force zone/region to specified value.")
p.add_argument('command',
        choices = ["start", "stop", "restart", "status"],
        help="""Command to issue for demo services.
           start/stop/restart: Start/stop/restart the demo environment.
           status: Show whether the environment is running or not.""")

ns = p.parse_args()

if ns.empty_nodes and ns.command not in ("stop", "restart"):
    p.error("-e, --empty-nodes is only used with stop and restart")

#
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd config file,
# very small, called ./helm-creds.yaml, which contains just the username and
# password for the helm repo you wish to use to get the helm charts.
#
myvarsbf = "my-vars.yaml"
myvarsf  = where("my-vars.yaml")
targetlabel = "Target"
nodecountlabel = "NodeCount"
chartvlabel = "ChartVersion"
try:
    with open(myvarsf) as mypf:
        myvars = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read user variables file {e}")

try:
    # Allow a commandline override of what's in the vars file
    target = myvars[targetlabel] if ns.target == None else ns.target
    zone = myvars["Zone"] if ns.zone == None else ns.zone

    email        = myvars["Email"]
    chartversion = myvars[chartvlabel]
    nodeCount    = myvars[nodecountlabel]
    license      = myvars["LicenseName"]
    repo         = myvars["HelmRepo"]
    repoloc      = myvars["HelmRepoLocation"]
    tlscoord     = myvars["RequireCoordTls"]
    tlsinternal  = myvars["RequireInternalTls"]
except KeyError as e:
    sys.exit(f"Unspecified configuration parameter {e} in {myvarsbf}")

def checkCLISetup() -> None:
    assert target in clouds
    if target == "aws":
        badAws = False
        if not writeableDir(awsdir):
            badAws = True
            err = f"Directory {awsdir} doesn't exist or has bad permissions."
        elif not readableFile(awsconfig):
            badAws = True
            err = f"File {awsconfig} doesn't exist or isn't readable."
        elif not readableFile(awscreds):
            badAws = True
            err = f"File {awscreds} doesn't exist or isn't readable."
        if badAws:
            print(err)
            sys.exit("Have you run aws configure?")
    elif target == "az":
        azuredir = os.path.expanduser("~/.azure")
        if not writeableDir(azuredir):
            print(f"Directory {azuredir} doesn't exist or isn't readable.")
            sys.exit("Have you run az login and az configure?")
    elif target == "gcp":
        gcpdir = os.path.expanduser("~/.config/gcloud")
        if not writeableDir(gcpdir):
            print("Directory {gcpdir} doesn't exist or isn't readable.")
            sys.exit("Have you run gcloud init?")

checkCLISetup()

# Set the region and zone from the location. We assume zone is more precise and
# infer the region from the zone.
def getRegionFromZone(zone: str) -> str:
    region = zone
    if target == "gcp":
        assert re.fullmatch(r"-[a-e]", zone[-2:]) != None
        region = zone[:-2]

    # Azure and GCP assume the user is working potentially with multiple
    # locations. On the other hand, AWS assumes a single region in the config
    # file, so make sure that the region in the AWS config file and the one set
    # in my-vars are consistent, just to avoid accidents.
    if target == "aws":
        awsregion = runCollect("aws configure get region".split())
        if awsregion != region:
            sys.exit(textwrap.dedent(f"""\
                    Region {awsregion} specified in your {awsconfig} doesn't
                    match region {region} set in your {myvarsbf} file. Cannot
                    continue execution. Please ensure these match and
                    re-run."""))

    return region

region = getRegionFromZone(zone)

def checkRSAKey() -> None:
    if readableFile(rsa) and readableFile(rsaPub):
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

checkRSAKey()

# Verify the email looks right, and extract username from it
# NB: username goes in GCP labels, and GCP requires labels to fit RFC-1035
emailparts = email.split('@')
if not (len(emailparts) == 2 and "." in emailparts[1]):
    sys.exit(f"Email specified in {myvarsbf} must be a full email address")
username = re.sub(r"[^a-zA-Z0-9]", "-", emailparts[0]).lower() # RFC-1035
codelen = min(3, len(username))
code = username[:codelen]

# Verify the cloud target is set up correctly Gather up other related items
# based on which cloud target it is.
#
if target == "aws":
    instanceType = myvars["AWSInstanceType"]
    bastionInstanceType = myvars["AWSBastionInstanceType"]
elif target == "az":
    instanceType = myvars["AzureVMType"]
    bastionInstanceType = myvars["AzureBastionVMType"]
elif target == "gcp":
    instanceType = myvars["GCPMachineType"]
    bastionInstanceType = myvars["GCPBastionMachineType"]
else:
    sys.exit("Cloud target '{t}' specified for '{tl}' in '{m}' not one of "
            "{c}".format(t = target, tl = targetlabel, m = myvarsbf,
                c = ", ".join(clouds)))

# Terraform files are in a directory named for target
tfdir       = where(target)
gcskeyfile  = tfdir + "/" + gcskeyfbn
tf          = f"terraform -chdir={tfdir}"
for d in [templatedir, tmpdir, tfdir]:
    assert writeableDir(d)

# Check the format of the chart version
components = chartversion.split('.')
if len(components) != 3 or not all(map(str.isdigit, components)):
    sys.exit(f"The {chartvlabel} in {myvarsbf} field must be of the form "
            f"x.y.z, all numbers; {chartversion} is not of a valid form")

# The yaml files for the coordinator and worker specify they should be on
# different nodes, so we need a 2-node cluster at minimum.
if nodeCount < 2:
    sys.exit(f"Must have at least {minnodes} nodes; {nodeCount} set for "
            f"{nodecountlabel} in {myvarsbf}.")

# Check the license file
licensebf = f"{license}.license"
licensef = where(licensebf)
if not readableFile(licensef):
    sys.exit(f"Your {myvarsbf} file specifies a license named {license} "
            f"located at {licensef} but no readable file exists there.")

# Generate a unique octet for our subnet. Use that octet with the 'code' we
# generated above as part of a short name we can use to mark resources we
# create.
s = username + zone
octet = int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 256
shortname = code + str(octet).zfill(3)

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
helmcredsbf = "helm-creds.yaml"
helmcredsf  = where("helm-creds.yaml")
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
myvars |= helmcreds

#
# Create some names for some cloud resources we'll need
#
clustname = shortname + "cl"
bucket = shortname + "bk"
storageacct = shortname + "sa"
resourcegrp = shortname + "rg"

templates = {}
releases = {}
charts = {}
modules = ["hive", "ranger", "enterprise"]
for module in modules:
    templates[module] = f"{module}_v.yaml"
    releases[module] = f"{module}-{shortname}"
    charts[module] = f"starburst-{module}"

# Portfinder service

starburstsrv = [ "starburst", "ranger" ]
svcports    = {
        "ranger":    { "local": 6080, "remote": 6080 },
        "apiserv":   { "local": 2153, "remote": 443  }
        }
if tlscoord:
    svcports |= { "starburst": { "local": 8443, "remote": 8443 } }
else:
    svcports |= { "starburst": { "local": 8080, "remote": 8080 } }

portoffset = { "aws": 0, "az": 1, "gcp": 2 }

# Local connections are on workstation, so offset to avoid collision
def getLclPort(service: str) -> int:
    return svcports[service]["local"] + portoffset[target]

# Remote connections are all to different machines, so they don't need offset
def getRmtPort(service: str) -> int:
    return svcports[service]["remote"]

#
# Important announcements to the user!
#

def announce(s):
    print(f"==> {s}")

sqlstr = "Issued 🢩 "

def announceSqlStart(s):
    print(f"{sqlstr}⟦{s}⟧")

def announceSqlEnd(s):
    print(" " * len(sqlstr) + f"⟦{s}⟧ 🢨 Done!")

def announceLoud(lines: list) -> None:
    maxl = max(map(len, lines))
    lt = "┃⮚ "
    rt = " ⮘┃"
    p = ["{l}{t}{r}".format(l = lt, t = i.center(maxl), r = rt) for i in lines]
    pmaxl = maxl + len(lt) + len(rt)
    print('┏' + '━' * (pmaxl - 2) + '┓')
    for i in p:
        print(i)
    print('┗' + '━' * (pmaxl - 2) + '┛')

def announceBox(s):
    boundary = 80 # maximum length to wrap to
    bl = '║ '
    br = ' ║'
    hz = '═'
    ul = '╔'
    ur = '╗'
    ll = '╚'
    lr = '╝'
    inner = boundary - len(bl) - len(br)
    lines = textwrap.wrap(s, width = inner, break_on_hyphens = False)
    maxl = max(map(len, lines))
    topbord = ul + hz * (maxl + 2) + ur
    botbord = ll + hz * (maxl + 2) + lr
    print(topbord)
    for l in lines:
        print(bl + l.ljust(maxl) + br)
    print(botbord)

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

def parameteriseTemplate(template, targetDir, varsDict):
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
                lstrip_blocks = True)
        t = env.get_template(template)
        output = t.render(varsDict)
    except jinja2.TemplateNotFound as e:
        print(f"Couldn't read {template} from {templatedir} due to {e}")
        raise

    changed = replaceFile(yamltmp, output)
    return changed, yamltmp

def getOutputVars() -> dict:
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
    return env

# Azure does some funky stuff with usernames for databases: It interposes a
# gateway in front of the database that forwards connections from
# username@hostname to username at hostname (supplied separately). So we must
# supply usernames in different formats for AWS and Azure.
def generateDatabaseUsers(env: dict) -> None:
    for db in ["mysql", "postgres", "evtlog"]:
        env[db + "_user"] = dbuser
        if target == "az":
            env[db + "_user"] += "@" + env[db + "_address"]

class KubeContextError(Exception):
    pass

def updateKubeConfig(kubecfg: str = None) -> None:
    # Phase I: Write in the new kubectl config file as-is
    announce(f"Updating kube config file")
    if target == "aws":
        assert kubecfg != None
        replaceFile(kubecfgf, kubecfg)
        print(f"wrote out kubectl file to {kubecfgf}")
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
                    "https://{h}:{p}".format(c = cluster, h = thishost, p =
                        getLclPort("apiserv")).split())
            runStdout(f"kubectl config set-cluster {cluster} "
                    "--insecure-skip-tls-verify=true".split())
            return
    raise KubeContextError(f"No active {kube} context within:\n{c}")

def getMyPublicIp() -> str:
    announce("Getting public IP address")
    try:
        i = runCollect("dig +short myip.opendns.com @resolver1.opendns.com "
                "-4".split())
    except CalledProcessError as e:
        sys.exit("Unable to reach the internet. Are your DNS resolvers set "
                "correctly?")

    try:
        myIp = ipaddress.ip_address(i)
        text = announceBox(f"Your visible IP address is {myIp}. Ingress to "
                "your newly-created bastion server will be limited to this "
                "address exclusively.")
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

def waitUntilNodesReady(minnodes: int) -> float:
    numer = 0
    denom = 0
    r = runTry(f"{kube} get no --no-headers".split())
    if r.returncode == 0:
        lines = r.stdout.splitlines()
        denom = len(lines)
        for line in lines:
            cols = line.split()
            assert len(cols) == 5
            if cols[1] == "Ready":
                # We've found a node that's ready. Count it.
                numer += 1
    denom = max(denom, minnodes)
    assert numer <= denom
    return float(numer) / float(denom)

def waitUntilPodsReady(mincontainers: int, namespace: str = None) -> float:
    numer = 0
    denom = 0
    ns = f" --namespace {namespace}" if namespace != None else ""
    r = runTry(f"{kube}{ns} get po --no-headers".split())
    if r.returncode == 0:
        lines = r.stdout.splitlines()
        for line in lines:
            cols = line.split()
            assert len(cols) == 5
            readyratio = cols[1].split('/')
            contready = int(readyratio[0])
            conttotal = int(readyratio[1])
            assert contready <= conttotal # common sense
            denom += conttotal

            # Since the cluster is brand-new and launching, we would only
            # expect pods to be advancing towards the Running/Ready state.
            # But some of GCP's K8S system pods have a habit of crashing on
            # start. So we have to check not just the number ready, but that
            # they're not terminating. https://tinyurl.com/54ramy8k 
            if cols[2] == "Terminating":
                continue # None count since they're terminating

            # Now they're either Running or heading there.
            numer += contready
    denom = max(denom, mincontainers)
    assert numer <= denom
    return float(numer) / float(denom)

def waitUntilDeploymentsAvail(minreplicas: int, namespace: str = None) \
        -> float:
    numer = 0
    denom = 0
    ns = f" --namespace {namespace}" if namespace != None else ""
    r = runTry(f"{kube}{ns} get deployments --no-headers".split())
    if r.returncode == 0:
        lines = r.stdout.splitlines()
        for line in lines:
            cols = line.split()
            assert len(cols) == 5
            readyratio = cols[1].split('/')
            repready = int(readyratio[0])
            reptotal = int(readyratio[1])
            assert repready <= reptotal
            numer += repready
            denom += reptotal
    denom = max(denom, minreplicas)
    assert numer <= denom
    return float(numer) / float(denom)

def loadBalancerResponding(service: str) -> bool:
    assert service in starburstsrv
    port = getLclPort(service)

    # It is assumed this function will only be called once the ssh tunnels
    # have been established between the localhost and the bastion host
    if service == "starburst":
        url = "{m}://{h}:{p}/ui/login.html".format(m = "https" if
                tlscoord else "http", h = prestohost, p = port)
    elif service == "ranger":
        url = f"http://{thishost}:{port}/login.jsp"

    try:
        r = requests.get(url)
        return r.status_code == 200
    except requests.exceptions.ConnectionError as e:
        pass
    return False

def waitUntilLoadBalancersUp(services: list, namespace: str = None,
        checkConnectivity: bool = False) -> float:
    numer = 0
    denom = 0
    ns = f" --namespace {namespace}" if namespace != None else ""
    r = runTry(f"{kube}{ns} get svc -ojson".split())
    if r.returncode == 0:
        servs = json.loads(r.stdout)
        for s in servs["items"]:
            # Metadata section
            meta = s["metadata"] # this should always be present
            assert meta["namespace"] == namespace # we only asked for this
            if not "name" in meta:
                continue
            name = meta["name"]
            if not name in services:
                continue
            denom += 1 # found one we care about it

            # Status section - now see if its IP is allocated yet
            if not "status" in s:
                continue
            status = s["status"]
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
                host = ingress0["ip"]
            elif "hostname" in ingress0:
                host = ingress0["hostname"]
            else:
                continue
            if not len(host) > 0:
                continue

            # Has to actually respond to an HTTP GET
            if checkConnectivity and not loadBalancerResponding(name):
                continue

            # Found one service load balancer running
            numer += 1
    assert numer <= denom
    return float(numer) / float(denom)

def waitUntilApiServerResponding() -> float:
    # It is assumed this function will only be called once the ssh tunnels
    # have been established between the localhost and the bastion host
    url = "https://{h}:{p}/".format(h = thishost, p = getLclPort("apiserv"))
    try:
        r = requests.get(url, verify = False) # ignore certificate
        # Either forbidden (403), unauthorised (403) or 200 are acceptable
        if r.status_code in (401, 403, 200):
            return 1.0 # all done!
    except requests.exceptions.ConnectionError as e:
        pass
    return 0.0

def spinWait(waitFunc: Callable[[], float]) -> None:
    anim1 = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
    anim2 = ['⣷', '⣯', '⣟', '⡿', '⢿', '⣻', '⣽', '⣾']
    maxlen = 0
    f = min(len(anim1), len(anim2))
    barlength = 64
    i = 0
    pct = 0.0
    while pct < 1.0:
        pct = waitFunc()
        assert(pct <= 1.0)
        c = int(pct * barlength)
        arrow = '⇒' if c > 0 else ""
        if c > 1:
            arrow = (c - 1) * '═' + arrow
        r = barlength - c
        space = ' '*r
        s = '   ' + anim1[i % f] + '╞' + arrow + space + '╡' + anim2[i % f]
        maxlen = max(maxlen, len(s))
        print(s, end='\r', flush=True)
        if pct == 1.0:
            print(' ' * maxlen, end='\r')
            return
        i += 1
        time.sleep(1)

# A class for recording ssh tunnels
class Tunnel:
    def __init__(self, shortname: str, bastionIp: str, lPort: int, rAddr: str,
            rPort: int):
        self.shortname = shortname
        self.bastion = bastionIp
        self.lport = lPort
        self.raddr = rAddr
        self.rport = rPort
        self.p = None
        cmd = "ssh -N -L{p}:{a}:{k} ubuntu@{b}".format(p = lPort, a = rAddr, k
                = rPort, b = bastionIp)
        print(cmd)
        self.p = subprocess.Popen(cmd.split())
        announce("Created tunnel " + str(self))

    def __del__(self):
        announce("Terminating tunnel " + str(self))
        if self.p != None:
            self.p.terminate()

    def __str__(self):
        tgtname = self.shortname
        if len(self.raddr) < 16:
            tgtname = "[{n}]{h}".format(n = self.shortname, h = self.raddr)
        return "PID {p}: localhost:{l} -> {ra}:{rp}".format(p =
                self.p.pid if self.p != None else "UNKNOWN", l = self.lport,
                ra = tgtname, rp = self.rport)

# Input dictionary is the output variables from Terraform.
def establishBastionTunnel(env: dict) -> Tunnel:
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
    print(cmd)
    hostkeys = runCollect(cmd.split())
    print("Adding {n} host keys from bastion to {k}".format(n =
        len(hostkeys.splitlines()), k = knownhosts))
    appendToFile(knownhosts, hostkeys)

    # Start up the tunnel to the Kubernetes API server
    tun = Tunnel("k8s-apiserver", env["bastion_address"],
            getLclPort("apiserv"), env["k8s_api_server"],
            getRmtPort("apiserv"))

    # Now that the tunnel is in place, update our kubecfg with the address to
    # the tunnel, keeping everything else in place
    updateKubeConfig(env["kubectl_config"] if "kubectl_config" in env
            else None)

    # Ensure that we can talk to the api server
    announce("Waiting for api server to respond")
    spinWait(lambda: waitUntilApiServerResponding())
    return tun

def addAwsAuthConfigMap(workerIamRoleArn: str) -> None:
    # If we've already got an aws auth config map, we're done
    r = runTry(f"{kube} describe configmap -n kube-system aws-auth".split())
    if r.returncode == 0:
        announce("aws-auth configmap already installed")
        return
    # Parameterise the aws auth config map template with the node role arn
    changed, yamltmp = parameteriseTemplate(awsauthcm, tfdir, { "NodeRoleARN":
        workerIamRoleArn })
    # Nodes should start joining after this
    announce("Adding aws-auth configmap to cluster")
    runStdout(f"{kube} apply -f {yamltmp}".split())

def ensureClusterIsStarted(skipClusterStart: bool) -> dict:
    env = myvars
    env |= {
        "BastionInstanceType": bastionInstanceType,
        "BucketName":          bucket,
        "ClusterName":         clustname,
        "DBName":              dbschema,
        "DBNameEventLogger":   dbevtlog,
        "DBPassword":          dbpwd,
        "DBUser":              dbuser,
        "InstanceType":        instanceType,
        "MaxPodsPerNode":      maxpodpnode,
        "MyCIDR":              mySubnetCidr,
        "MyPublicIP":          getMyPublicIp(),
        "NodeCount":           nodeCount,
        "SshPublicKey":        getSshPublicKey(),
        "Region":              region,
        "ShortName":           shortname,
        "Target":              target,
        "UserName":            username,
        "Zone":                zone
        }
    assert target in clouds
    if target == "az":
        env["ResourceGroup"] = resourcegrp
        env["StorageAccount"] = storageacct
    parameteriseTemplate(tfvars, tfdir, env)

    if not skipClusterStart:
        announce("Starting terraform run")
        t = time.time()
        runStdout(f"{tf} init -input=false".split())
        runStdout(f"{tf} apply -auto-approve -input=false".split())
        announce("terraform run completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

    # Get variables returned from terraform run
    env = getOutputVars()

    # Generate the usernames for the databases
    generateDatabaseUsers(env) # Modify dict in-place

    # Having set up storage, we've received some credentials for it that we'll
    # need later. For GCP, write out a key file that Hive will use to access
    # GCS. For Azure, just set a value we'll use for the starburst values file.
    if target == "gcp":
        replaceFile(gcskeyfile, env["object_key"])
        env["gcskeyfile"] = gcskeyfile
    elif target == "az":
        env["adls_access_key"] = env["object_key"]

    # Start up the ssh tunnel to the bastion, so we can run kubectl
    tun = establishBastionTunnel(env)
    toreap.append(tun) # Save the reference so it doesn't get destroyed

    # For AWS, the nodes will not join until we have added the node role ARN to
    # the aws-auth-map-cn.yaml.
    if target == "aws":
        addAwsAuthConfigMap(env["worker_iam_role_arn"])

    # Don't continue until all nodes are ready
    announce("Waiting for nodes to come online")
    spinWait(lambda: waitUntilNodesReady(nodeCount))

    # Don't continue until all K8S system pods are ready
    announce("Waiting for K8S system pods to come online")
    spinWait(lambda: waitUntilPodsReady(nodeCount*2, "kube-system"))
    return env

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

def startPortForward(bastionIp: str) -> None:
    # should be nodeCount - 1 workers with 1 container each, 2 containers for
    # the coordinator, and 2 containers each for Hive and Ranger
    announce("Waiting for pods to be ready")
    spinWait(lambda: waitUntilPodsReady(nodeCount + 5, namespace))

    # coordinator, worker, hive, ranger, 1 replica each = 4 replicas
    announce("Waiting for deployments to be available")
    spinWait(lambda: waitUntilDeploymentsAvail(4, namespace))

    # now the load balancers need to be running with their IPs assigned
    announce("Waiting for load-balancers to launch")
    spinWait(lambda: waitUntilLoadBalancersUp(starburstsrv, namespace))

    #
    # Get the DNS name of the load balancers we've created
    #
    lbs = {}
    ksvcs = json.loads(runCollect(f"{kubens} get services "
        "--output=json".split() + starburstsrv))

    # Go through the named K8S services and find the loadBalancers
    for ksvc in ksvcs["items"]:
        ingress = ksvc["status"]["loadBalancer"]["ingress"]
        assert len(ingress) == 1
        ingress = ksvc["status"]["loadBalancer"]["ingress"][0]
        if "hostname" in ingress:
            lbs[ksvc["metadata"]["name"]] = ingress["hostname"]
        elif "ip" in ingress:
            lbs[ksvc["metadata"]["name"]] = ingress["ip"]
        else:
            sys.exit("Could not find either hostname or ip in {ingress}")

    # we should have a load balancer for every service we'll forward
    assert len(lbs) == len(starburstsrv)
    for svc in starburstsrv:
        toreap.append(Tunnel(svc, bastionIp, getLclPort(svc), lbs[svc],
            getRmtPort(svc)))

    # make sure the load balancers are actually responding
    announce("Waiting for load-balancers to start responding")
    spinWait(lambda: waitUntilLoadBalancersUp(starburstsrv, namespace,
        checkConnectivity = True))

class ApiError(Exception):
    pass

def retry(f, maxretries: int, err: str) -> requests.Response:
    retries = 0
    stime = 1
    while True:
        try:
            r = f()
            if r.status_code == 503:
                time.sleep(0.5)
                continue
            # All good -- we exit here.
            if retries > 0:
                print(f"Succeeded on \"{err}\" after {retries} retries")
            return r
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect: \"{err}\"; retries={retries}; sleep={stime}")
            if retries > maxretries:
                print(f"{maxretries} retries exceeded!")
                raise
            time.sleep(stime)
            retries += 1
            stime <<= 1

def issuePrestoCommand(command: str, verbose = False) -> list:
    httpmaxretries = 10
    if verbose: announceSqlStart(command)
    url = "{m}://{h}:{p}/v1/statement".format(m = "https" if tlscoord
            else "http", h = prestohost, p = getLclPort("starburst"))
    hdr = { "X-Trino-User": trinouser }
    if tlscoord:
        authtype = requests.auth.HTTPBasicAuth(trinouser, trinopass)
    else:
        authtype = None
    r = retry(lambda: requests.post(url, headers = hdr, auth = authtype, data =
        command), maxretries = httpmaxretries, err = f"POST [{command}]")

    data = []
    while True:
        r.raise_for_status()
        assert r.status_code == 200
        j = r.json()
        if "data" in j:
            data += j["data"]
        if "nextUri" not in j:
            if "error" in j:
                raise ApiError("Error executing SQL '{s}': error {e}".format(s =
                    command, e = str(j["error"])))
            if verbose: announceSqlEnd(command)
            return data # the only way out is success, or an exception
        r = retry(lambda: requests.get(j["nextUri"], headers = hdr), maxretries
                = httpmaxretries, err = f"GET nextUri [{command}]")

def copySchemaTables(srcCatalog: str, srcSchema: str,
        dstCatalogs: list, dstSchema: str, hiveTarget: str):
    # fetch our source tables
    stab = issuePrestoCommand(f"show tables in {srcCatalog}.{srcSchema}")
    srctables = [t[0] for t in stab]

    threads = []
    for dstCatalog in dstCatalogs:
        # We never want to write data to these schemas!
        if dstCatalog in avoidcat + [srcCatalog]: continue

        #
        # First, we need to make sure our 'dbschema' schema is found in every
        # database. Hive needs to be treated specially.
        #
        stable = issuePrestoCommand(f"show schemas in {dstCatalog}")
        schemas = [s[0] for s in stable]
        dsttables = []
        if dstSchema not in schemas:
            clause = " with (location = '{l}/{s}')".format(l = hiveTarget,
                    s = dstSchema) if dstCatalog == "hive" else ""
            issuePrestoCommand("create schema {c}.{s}{w}".format(c = dstCatalog,
                s = dstSchema, w = clause), verbose = True)
        else:
            dtab = issuePrestoCommand("show tables in {c}.{s}".format(c =
                dstCatalog, s = dstSchema))
            dsttables = [d[0] for d in dtab]

        #
        # Now copy the data over from our source tables, one by one
        #
        for srctable in srctables:
            if srctable not in dsttables:
                c = f"create table {dstCatalog}.{dstSchema}.{srctable} as " \
                        f"select * from {srcCatalog}.{srcSchema}.{srctable}"
                t = threading.Thread(target = issuePrestoCommand, args = (c,True,))
                threads.append(t)
                t.start()

    for t in threads:
        t.join()

def eraseBucketContents(env: dict):
    # Delete everything in the S3 bucket
    assert target in clouds

    cmd = ""
    if target == "aws":
        cmd = "aws s3 rm s3://{b}/{d} --recursive".format(b = bucket, d =
                dbschema)
    elif target == "az" and "adls_access_key" in env:
        cmd = ("az storage fs directory delete -y --file-system {b} "
                "--account-name {s} --account-key {a} --name /{d}").format(b =
                        bucket, s = storageacct, a = env["adls_access_key"], d
                        = dbschema)
    elif target == "gcp" and "object_address" in env:
        cmd = "gsutil rm -rf {b}/{d}".format(b = env["object_address"], d =
                dbschema)

    if cmd != "":
        announce(f"Deleting contents of bucket {bucket}")
        try:
            runStdout(cmd.split())
        except CalledProcessError as e:
            print(f"Unable to erase bucket {bucket} (already empty?)")

def loadDatabases(hive_location):
    if target == "aws":
        hive_location = f"s3://{bucket}"
    elif target == "az":
        hive_location = f"abfs://{bucket}@{hive_location}"

    # First copy from tpch to hive...
    announce(f"populating tables in {hivecat}")
    copySchemaTables(tpchcat, tpchschema, [hivecat], dbschema, hive_location)

    # Then copy from hive to everywhere in parallel
    ctab = issuePrestoCommand("show catalogs")
    dstCatalogs = [c[0] for c in ctab if c[0] not in avoidcat + [hivecat]]
    announce("populating tables in {}".format(", ".join(dstCatalogs)))
    copySchemaTables(hivecat, dbschema, dstCatalogs, dbschema, "")

def installSecret(name, file):
    r = runTry(f"{kubens} get secrets {name}".split())
    # if the secret with that name doesn't yet exist, create it
    if r.returncode != 0:
        runStdout(f"{kubens} create secret generic {name} --from-file "
                f"{file}".split())
    announce(f"Secret {file} installed as \"{name}\"")

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
            helm("repo update")
            return

    try:
        helm(f"repo add --username {repouser} --password "
            f"{repopass} {repo} {repoloc}")
    except CalledProcessError as e:
        print("Could not install (or verify installation of) "
                f"{repo} at {repoloc}")
        raise

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
        grace = 120 # 2 minutes
        runStdout(f"{kube} delete namespace {namespace} "
                f"--grace-period={grace}".split())
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

def helmWhichChartInstalled(module: str) -> Optional[Any]:
    chart = None
    release = releases[module] # Get release name for module name
    installed = helmGetReleases()
    if release in installed:
        chart = installed[release] # Get chart for release
    return chart

# Returns a bool indicating if the hive postgres database might have been
# created--either during an install, or because we revved up a version
def helmInstallRelease(module: str, env = {}) -> bool:
    hivereset = False

    env |= myvars | \
            { "BucketName":         bucket,
              "DBName":             dbschema,
              "DBNameEventLogger":  dbevtlog,
              "DBPassword":         dbpwd,
              "PrestoHost":         prestohost,
              "PrestoPort":         getRmtPort("starburst"),
              "RequireCoordTls":    tlscoord,
              "RequireInternalTls": tlsinternal,
              "StorageAccount":     storageacct,
              "TrinoUser":          trinouser,
              "TrinoPass":          trinopass,
              "mysql_port":         dbports["mysql"],
              "postgres_port":      dbports["postgres"],
              "target":             target }

    # Parameterise the yaml file that configures the helm chart install. The
    # function returns a tuple, indicating whether the helm chart values file
    # changed, and the location of that same (parameterised) values file.
    changed, yamltmp = parameteriseTemplate(templates[module], tmpdir, env)

    chart = helmWhichChartInstalled(module)
    newchart = charts[module] + "-" + chartversion # which one to install?

    workingrepo = repo
    # There is a bug in Starburst's helm charts where load-balancers can only
    # be on the unsecured port 8080. Fix this manually here.
    if module == "enterprise" and (tlscoord or tlsinternal):
        # Only write if the directory doesn't yet exist
        targetdir = f"/tmp/repo-{repo}-{chartversion}"
        if not os.path.exists(targetdir):
            helm("pull {p}/{c} --version {v} --untar --untardir {d}".format(p =
                repo, c = charts[module], v = chartversion, d = targetdir))
            runStdout(f"patch -d {targetdir} -p1 -i {patchfile}".split())
            changed = True
        workingrepo = targetdir

    if chart == None: # Nothing installed yet, so we need to install
        announce(f"Installing chart {newchart} using helm")
        helm("{h} install {r} {w}/{c} -f {y} --version {v}".format(h = helmns,
            r = releases[module], w = workingrepo, c = charts[module], y =
            yamltmp, v = chartversion))
        if module == "hive":
            hivereset = True # freshly installed -> new postgres
    # If either the chart values file changed, or we need to update to a
    # different version of the chart, then we have to upgrade
    elif changed or chart != newchart:
        astr = "Upgrading release {}".format(releases[module])
        if chart != newchart:
            astr += ": {oc} -> {nc}".format(oc = chart, nc = newchart)
        announce(astr)
        helm("{h} upgrade {r} {w}/{c} -f {y} --version {v}".format(h = helmns,
            r = releases[module], w = workingrepo, c = charts[module], y =
            yamltmp, v = chartversion))

        # Hive postgres DB will be rebuilt only if we rev a version
        if module == "hive" and chart != newchart:
            hivereset = True
    else:
        print(f"{chart} values unchanged ➼ avoiding helm upgrade")
    return hivereset

def helmUninstallRelease(release: str) -> None:
    helm(f"{helmns} uninstall {release}")

# Normalise CPU to 1000ths of a CPU ("mCPU")
def normaliseCPU(cpu) -> int:
    if cpu.endswith("m"):
        cpu = cpu[:-1]
        assert cpu.isdigit()
        cpu = int(cpu)
    else:
        assert cpu.isdigit()
        cpu = int(cpu) * 1000
    return cpu

# Normalise memory to Ki
def normaliseMem(mem) -> int:
    normalise = { "Ki": 0, "Mi": 10, "Gi": 20 }
    assert len(mem) > 2
    unit = mem[-2:]
    assert unit.isalpha()
    assert unit in normalise
    mem = mem[:-2]
    assert mem.isdigit()
    mem = int(mem)
    mem <<= normalise[unit]
    return mem

def getMinNodeResources() -> tuple:
    n = json.loads(runCollect(f"{kube} get nodes -o json".split()))["items"]
    p = json.loads(runCollect(f"{kube} get pods -A -o json".split()))["items"]

    nodes = {t["metadata"]["name"]: {"cpu":
        normaliseCPU(t["status"]["allocatable"]["cpu"]), "mem":
        normaliseMem(t["status"]["allocatable"]["memory"])} for t in n}
    assert len(nodes) >= minnodes

    for q in p: # for every pod
        # If it's Starburst pods, then skip them
        if q["metadata"]["namespace"] == namespace:
            continue

        try:
            nodename = q["spec"]["nodeName"] # see what node it's on
        except KeyError as e:
            qpt = json.dumps(q)
            ppt = json.dumps(p)
            print(f"'nodeName' not in {qpt}; pods: {ppt}, e: {e}")
            raise

        assert nodename in nodes
        x = nodes[nodename]
        for c in q["spec"]["containers"]: # for every container in pod
            r = c["resources"]
            if "requests" in r:
                t = r["requests"]
                if "cpu" in t:
                    x["cpu"] -= normaliseCPU(t["cpu"])
                if "memory" in t:
                    x["mem"] -= normaliseMem(t["memory"])

    mincpu = minmem = 0
    for node, allocatable in nodes.items():
        cpu = allocatable["cpu"]
        if mincpu == 0 or mincpu > cpu:
            mincpu = cpu
        mem = allocatable["mem"]
        if minmem == 0 or minmem > mem:
            minmem = mem
    assert mincpu > 0 and minmem > 0
    print("All nodes have >= {c}m CPU and {m}Ki mem after K8S "
            "system pods".format(c = mincpu, m = minmem))
    return mincpu, minmem

def planWorkerSize() -> dict:
    # Each worker or coordinator should get most of the CPU and memory on every
    # node. The remainder should be reserved for _either_ Ranger or Hive.
    c, m = getMinNodeResources()
    cpu = {}
    mem = {}
    cpu["worker"] = cpu["coordinator"] = (c >> 3) * 7
    mem["worker"] = mem["coordinator"] = (m >> 3) * 7
    print("Workers & coordinator get {c}m CPU and {m}Mi mem".format(c =
        cpu["worker"], m = mem["worker"] >> 10))
    cpu["ranger_admin"] = cpu["ranger_db"] = cpu["hive"] = cpu["hive_db"] = \
            c >> 4
    mem["ranger_admin"] = mem["ranger_db"] = mem["hive"] = mem["hive_db"] = \
            m >> 4
    assert cpu["worker"] + cpu["hive"] + cpu["hive_db"] <= c
    assert mem["worker"] + mem["hive"] + mem["hive_db"] <= m
    assert cpu["worker"] + cpu["ranger_admin"] + cpu["ranger_db"] <= c
    assert mem["worker"] + mem["ranger_admin"] + mem["ranger_db"] <= m
    print("Hive gets {c}m CPU and {m}Mi mem".format(c = cpu["hive"] +
        cpu["hive_db"], m = (mem["hive"] + mem["hive_db"]) >> 10))
    print("Ranger gets {c}m CPU and {m}Mi mem".format(c = cpu["ranger_admin"] +
        cpu["ranger_db"], m = (mem["ranger_admin"] + mem["ranger_db"]) >> 10))
    env = {f"{k}_cpu": f"{v}m" for k, v in cpu.items()}
    env |= {f"{k}_mem": "{m}Mi".format(m = v >> 10) for k, v in
        mem.items()}
    assert nodeCount >= minnodes
    env["workerCount"] = nodeCount - 1
    return env

def helmInstallAll(env):
    helmCreateNamespace()
    installSecret(repo, licensef)
    if tlscoord or tlsinternal:
        installSecret(keystorebf, keystoref)
    if tlsinternal:
        installSecret(sharedsecbf, sharedsecf)

    # For GCP, we'll need to store the secret for our GCS access in K8S
    if target == "gcp":
        installSecret(gcskeyname, gcskeyfile)
        env["gcskeyname"] = gcskeyname
        env["gskeyfbn"] = gcskeyfbn

    ensureHelmRepoSetUp(repo)
    capacities = planWorkerSize()
    env |= capacities
    hivereset = False
    for module in modules:
        hivereset = helmInstallRelease(module, env) or hivereset
    # If we've installed Hive for the first time, or if we revved the version
    # of the Hive helm chart, then it will have set up fresh the internal
    # PostgreSQL DB used for metadata, which means there also shouldn't be any
    # files in our filesystem, in order to be in sync. Do this to avoid errors
    # about finding existing files.
    if hivereset:
        eraseBucketContents(env)

    # Speed up the deployment of the updated pods by killing the old ones
    killAllTerminatingPods()

def deleteAllServices() -> None:
    # Explicitly deleting services gets rid of load balancers, which eliminates
    # a race condition that Terraform is susceptible to, where the ELBs created
    # by the load balancers endure while the cluster is destroyed, stranding
    # the ENIs and preventing the deletion of the associated subnets
    # https://github.com/kubernetes/kubernetes/issues/93390
    announce("Deleting all k8s services")
    runStdout(f"{kubens} delete svc --all".split())

def helmUninstallAll():
    for release, chart in helmGetReleases().items():
        try:
            announce(f"Uninstalling chart {chart}")
            helmUninstallRelease(release)
        except CalledProcessError as e:
            print(f"Unable to uninstall release {release}: {e}")
    helmDeleteNamespace()

def awsGetCreds():
    awsAccess = runCollect("aws configure get aws_access_key_id".split())
    awsSecret = runCollect("aws configure get aws_secret_access_key".split())
    return dict(AWSAccessKey=awsAccess, AWSSecretKey=awsSecret)

def announceReady(bastionIp: str) -> list:
    return ["Bastion: {b}".format(b = bastionIp)]

def svcStart(skipClusterStart: bool = False) -> list:
    # First see if there isn't a cluster created yet, and create the cluster.
    # This will create the control plane and workers.
    env = ensureClusterIsStarted(skipClusterStart)
    env["Region"] = region
    env |= awsGetCreds()
    helmInstallAll(env)
    startPortForward(env["bastion_address"])
    loadDatabases(env["object_address"])
    return announceReady(env["bastion_address"])

def isTerraformSettled(tgtResource: str = None) -> bool:
    tgt = ""
    if tgtResource != None:
        tgt = f"-target='{tgtResource}' "
    r = runTry(f"{tf} plan -input=false {tgt}"
            "-detailed-exitcode".split()).returncode
    return r == 0

def svcStop(emptyNodes: bool = False) -> None:
    # Re-establish the tunnel with the bastion, or our helm and kubectl
    # commands won't work.
    announce("Checking current Terraform status")
    if isTerraformSettled():
        announce("Re-establishing bastion tunnel")
        env = getOutputVars()
        try:
            tun = establishBastionTunnel(env)
            t = time.time()
            deleteAllServices()
            helmUninstallAll()
            eraseBucketContents(env)
            announce("nodes emptied in " + time.strftime("%Hh%Mm%Ss",
                time.gmtime(time.time() - t)))
            del tun # Get rid of the tunnel
        except CalledProcessError as e:
            announceBox(textwrap.dedent("""\
                    Your Terraform is set up, but your bastion host is not
                    responding. It might be a network issue, or it might be
                    your public IP address has changed since you set up. I will
                    try to destroy your terraform without unloading your pods
                    but you might have trouble on the destroy."""))

    if not emptyNodes:
        announce(f"Ensuring cluster {clustname} is deleted")
        t = time.time()
        runStdout(f"{tf} destroy -auto-approve".split())
        announce("tf destroy completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

def getCloudSummary() -> List[str]:
    if target == "aws":
        cloud = "Amazon Web Services"
    elif target == "az":
        cloud = "Microsoft Azure"
    else:
        cloud = "Google Cloud Services"
    return [f"Cloud: {cloud}",
        f"Region: {region}",
        f"Cluster: {nodeCount} × {instanceType}"]

def announceSummary() -> None:
    announceLoud(getCloudSummary())

announceSummary()

w = []
started = False

if ns.command in ("stop", "restart"):
    svcStop(ns.empty_nodes)

if ns.command in ("start", "restart"):
    w = svcStart(ns.skip_cluster_start)
    started = True
    announceBox(f"Your {rsaPub} public key has been installed into the "
            "bastion server, so you can ssh there now (user 'ubuntu').")

if ns.command == "status":
    announce("Fetching current status")
    started = isTerraformSettled()
    if started:
        env = getOutputVars()
        w = announceReady(env["bastion_address"])

y = getCloudSummary() + ["Service is " + ("started" if started else "stopped")]
if len(w) > 0:
    y += w

if ns.command in ("start", "restart") and started:
    y.append("These ssh tunnels are now running:")
    y += [str(i) for i in toreap]
    announceLoud(y)
    input("Press return key to quit and terminate tunnels!")
    sys.exit(0) # Tunnels destroyed on de-reference

announceLoud(y)
