#!python

import os, hashlib, argparse, sys, pdb, textwrap, requests, json, yaml, re
import subprocess, ipaddress, glob, threading, time, concurrent.futures, jinja2
from run import run, runShell, runTry, runStdout, runCollect
from subprocess import CalledProcessError
import psutil # type: ignore
from typing import Tuple, Iterable

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
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd configuration
# file, very small, called ./helm-creds.yaml, which contains just the username
# and password for the helm repo you wish to use to get the helm charts.
#
myvarsbf = "my-vars.yaml"
myvarsf  = where("my-vars.yaml")
awsvpnlabel = "AWSVPNInstanceIDs"
nodecountlabel = "NodeCount"
chartvlabel = "ChartVersion"
try:
    with open(myvarsf) as mypf:
        myvars = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read user variables file {e}")

try:
    email        = myvars["Email"]
    zone         = myvars["Zone"]
    chartversion = myvars[chartvlabel]
    nodeCount    = myvars[nodecountlabel]
    license      = myvars["LicenseName"]
    repo         = myvars["HelmRepo"]
    repoloc      = myvars["HelmRepoLocation"]
    awsvpns      = myvars[awsvpnlabel]
    azurevpns    = myvars["AzureVPNVnetNames"]
    gcpvpns      = myvars["GCPVPNInstanceNames"]
except KeyError as e:
    sys.exit(f"Unspecified configuration parameter {e} in {myvarsbf}")

# Check the format of the chart version
components = chartversion.split('.')
if len(components) != 3 or not all(map(str.isdigit, components)):
    sys.exit(f"The {chartvlabel} in {myvarsbf} field must be of the form "
            f"x.y.z, all numbers; {chartversion} is not of a valid form")

# Check the license file
licensebf = f"{license}.license"
licensef = where(licensebf)
if not readableFile(licensef):
    sys.exit(f"Your {myvarsbf} file specifies a license named {license} "
            f"located at {licensef} but no readable file exists there.")

# Verify the email looks right, and extract username from it
# NB: username goes in GCP labels, and GCP requires labels to fit RFC-1035
emailparts = email.split('@')
if not (len(emailparts) == 2 and "." in emailparts[1]):
    sys.exit(f"Email specified in {myvarsbf} must be a full email address")
username = re.sub(r"[^a-zA-Z0-9]", "-", emailparts[0]).lower() # RFC-1035
codelen = min(3, len(username))
code = username[:codelen]

# Generate a unique octet for our subnet. Use that octet with the 'code' we
# generated above as part of a short name we can use to mark resources we
# create.
s = username + zone
octet = int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 256
shortname = code + str(octet).zfill(3)

awsdir = os.path.expanduser("~/.aws")
awsconfig = os.path.expanduser("~/.aws/config")
awscreds = os.path.expanduser("~/.aws/credentials")

#
# Work out which cloud target based on the VPN lists.
#
if zone in awsvpns:
    target = "aws"
    instanceType = myvars["AWSInstanceType"]
    bastionInstanceType = myvars["AWSBastionInstanceType"]
elif zone in azurevpns:
    target = "az"
    instanceType = myvars["AzureVMType"]
    bastionInstanceType = myvars["AzureBastionVMType"]
elif zone in gcpvpns:
    target = "gcp"
    instanceType = myvars["GCPMachineType"]
    bastionInstanceType = myvars["GCPBastionMachineType"]
else:
    sys.exit(textwrap.dedent(f"""\
    Zone {zone} specified in {myvarsbf}, but is not listed in any of the VPN
    sections in {myvarsbf}. Please add it!"""))

# Set the region and zone from the location. We assume zone is more precise and
# infer the region from the zone.
region = zone
if target == "gcp":
    assert re.fullmatch(r"-[a-e]", zone[-2:]) != None
    region = zone[:-2]

# Azure and GCP assume the user is working potentially with multiple locations.
# On the other hand, AWS assumes a single region in the config file, so make
# sure that the region in the AWS config file and the one set in my-vars are
# consistent, just to avoid accidents.
if target == "aws":
    awsregion = runCollect("aws configure get region".split())
    if awsregion != region:
        sys.exit(textwrap.dedent(f"""\
                Region {awsregion} specified in your {awsconfig} doesn't match
                region {region} set in your {myvarsbf} file. Cannot continue
                execution. Please ensure these match and re-run."""))

if nodeCount < 3:
    sys.exit(f"Must have at least 3 nodes; {nodeCount} set for "
            f"{nodecountlabel} in {myvarsbf}.")

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

try:
    ipntwk = ipaddress.ip_network(mySubnetCidr)
except ValueError as e:
    print(f"It appears the 'MyCIDR' value in {myvarsbf} is not in the format "
            "x.x.x.x/mask: {e}")
    raise

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
myvars.update(helmcreds)

#
# Global variables.
#
clouds      = ("aws", "az", "gcp")
templatedir = where("templates")
tmpdir      = "/tmp"
rsa         = os.path.expanduser("~/.ssh/id_rsa")
rsaPub      = os.path.expanduser("~/.ssh/id_rsa.pub")
tfvars      = "variables.tf" # basename only, no path!
svcports    = { "presto": 8080, "ranger": 6080 }
dbports     = { "mysql": 3306, "postgres": 5432 }
tpchschema  = "tiny"
tpchcat     = "tpch"
hivecat     = "hive"
syscat      = "system"
forwarder   = where("az/forwarderSetup.sh")
tfdir       = where(target)
gcskeyname  = "gcs-keyfile"
gcskeyfbn   = f"key.json"
gcskeyfile  = tfdir + "/" + gcskeyfbn
tf          = f"terraform -chdir={tfdir}"
evtlogcat   = "postgresqlel"
avoidcat    = [tpchcat, syscat, evtlogcat]
dbschema    = "fdd"
dbevtlog    = "evtlog" # event logger PostgreSQL instance
dbuser      = "fdd"
dbpwd       = "a029fjg!>dfgBiO8"
namespace   = "starburst"
helmns      = f"--namespace {namespace}"
kube        = "kubectl"
kubecfgf    = os.path.expanduser("~/.kube/config")
kubens      = f"kubectl --namespace {namespace}"
azuredns    = "168.63.129.16"
minnodes    = 3
timeout     = "--timeout 1h"

for d in [templatedir, tmpdir, tfdir]:
    assert writeableDir(d)

# Generate a random octet

clustname = shortname + "cl"
bucket = shortname + "bk"
storageacct = shortname + "sa"
resourcegrp = shortname + "rg"

templates = {}
releases = {}
charts = {}
modules = ["hive", "ranger", "presto"]
for module in modules:
    templates[module] = f"{module}_v.yaml"
    releases[module] = f"{module}-{shortname}"
    charts[module] = f"{repo}/starburst-{module}"

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

def warnVpnConfig(privateDnsAddr: str = ""):
    s = textwrap.dedent(f"""\
            NB: Your VPC/VNET CIDR is listed as {mySubnetCidr}, which should be
            included in your routing table.""")

    ovpnfiles = glob.glob(os.path.expanduser("~/Library/Application Support/"
        "Tunnelblick/Configurations/*/Contents/Resources/config.ovpn"))
    if (l := len(ovpnfiles)) > 0:
        s += textwrap.dedent(""" \
                It looks like you're using Tunnelblick. To achieve this routing
                you could add 'route {netaddr} {netmask}' to your OpenVPN client
                config and reconnect Tunnelblick.""".format(netaddr =
                    ipntwk.network_address, netmask = ipntwk.netmask))

    if target == "az":
        s += textwrap.dedent(""" \
                For Azure, you also will need {p} and {a} listed as DNS
                resolvers, in that order, to access the new demo
                vnet.""".format(p = privateDnsAddr, a = azuredns))

    announceBox(s)

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
                    if match := re.match(r"# md5 ([\da-f]{32}) ver "
                            "(\d+\.\d+\.\d+)", fl):
                        if newmd5 == match.group(1) and \
                                chartversion == match.group(2):
                            # It's the same file. Don't bother writing it.
                            return False # didn't write
        # We have an old file, but the md5 doesn't match, indicating it has been
        # updated. We want to remove the old one in preparation for the update.
        os.remove(filepath)

    # some of the files being written contain secrets in plaintext, so don't
    # allow them to be read by anyone but the user
    os.umask(0)
    flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL # we are writing new one
    try:
        with open(os.open(path=filepath, flags=flags, mode=0o600), 'w') as fh:
            if ext in (".yaml", ".tf"):
                fh.write(f"# md5 {newmd5} ver {chartversion}\n")
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
    similar = f"{targetDir}/{root}-*{ext}"
    removeOldVersions(yamltmp, similar)

    # render the template with the parameters, and capture the result
    try:
        file_loader = jinja2.FileSystemLoader(templatedir)
        env = jinja2.Environment(loader = file_loader)
        t = env.get_template(template)
        output = t.render(varsDict)
    except jinja2.TemplateNotFound as e:
        print(f"Couldn't read {template} from {templatedir} due to {e}")
        raise

    changed = replaceFile(yamltmp, output)
    return changed, yamltmp

def getOutputVars() -> dict:
    env = json.loads(runCollect(f"{tf} output -json".split()))
    return {k: v["value"] for k, v in env.items()}

# Azure does some funky stuff with usernames for databases: It interposes a
# gateway in front of the database that forwards connections from
# username@hostname to username at hostname (supplied separately). So we must
# supply usernames in different formats for AWS and Azure.
def generateDatabaseUsers(env: dict) -> None:
    for db in ["mysql", "postgres", "evtlog"]:
        env[db + "_user"] = dbuser
        if target == "az":
            env[db + "_user"] += "@" + env[db + "_address"]

def updateKubeConfig(kubecfg: str) -> None:
    announce(f"Updating kube config file")
    if target == "aws":
        replaceFile(kubecfgf, kubecfg)
        print(f"wrote out kubectl file to {kubecfgf}")
    elif target == "az":
        runStdout(f"az aks get-credentials --resource-group {resourcegrp} "
                f"--name {clustname} --overwrite-existing".split())
    elif target == "gcp":
        runStdout(f"gcloud container clusters get-credentials {clustname} "
                f"--region {zone} --internal-ip".split())

def getMyPublicIp() -> str:
    i = runCollect("dig +short myip.opendns.com @resolver1.opendns.com "
            "-4".split())
    try:
        myIp = ipaddress.ip_address(i)
        # TODO: This statement won't actually be true until we exclude VPN
        # access for AWS and GCP, and restrict home access for Azure too.
        text = announceBox(f"Your visible IP address is {myIp}. Ingress to your "
                "newly-created bastion server will be limited to this address "
                "exclusively.")
        return myIp
    except ValueError:
        print(f"Unable to retrieve my public IP address; got {i}")
        raise

def getSshPublicKey() -> str:
    try:
        with open(rsaPub) as rf:
            return rf.read()
    except IOError as e:
        sys.exit(f"Unable to read your public RSA key {rsaPub}")

def ensureClusterIsStarted(skipClusterStart: bool) -> dict:
    env = myvars
    env.update({
        "BastionInstanceType": bastionInstanceType,
        "BucketName":          bucket,
        "ClusterName":         clustname,
        "DBName":              dbschema,
        "DBNameEventLogger":   dbevtlog,
        "DBPassword":          dbpwd,
        "DBUser":              dbuser,
        "InstanceType":        instanceType,
        "MyCIDR":              mySubnetCidr,
        "MyPublicIP":          getMyPublicIp(),
        "NodeCount":           nodeCount,
        "SshPublicKey":        getSshPublicKey(),
        "Region":              region,
        "ShortName":           shortname,
        "Target":              target,
        "UserName":            username,
        "Zone":                zone
        })
    assert target in clouds
    if target == "aws":
        env["VpnInstanceId"] = awsvpns[zone]
    elif target == "az":
        vpn = azurevpns[zone]
        env["VpnVnetResourceGroup"] = vpn["resourceGroup"]
        env["VpnVnetName"] = vpn["name"]
        env["ResourceGroup"] = resourcegrp
        env["ForwarderScript"] = forwarder
        env["StorageAccount"] = storageacct
    elif target == "gcp":
        env["VpnInstanceId"] = gcpvpns[zone]
    parameteriseTemplate(tfvars, tfdir, env)

    if not skipClusterStart:
        runStdout(f"{tf} init -input=false -upgrade".split())
        t = time.time()
        runStdout(f"{tf} apply -auto-approve -input=false".split())
        announce("tf apply completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

    # Get variables returned from terraform run
    env = getOutputVars()
    generateDatabaseUsers(env) # Modify dict in-place

    # Having set up storage, we've received some credentials for it that we'll
    # need later. For GCP, write out a key file that Hive will use to access
    # GCS. For Azure, just set a value we'll use for the presto values file.
    if target == "gcp":
        replaceFile(gcskeyfile, env["object_key"])
        env["gcskeyfile"] = gcskeyfile
    elif target == "az":
        env["adls_access_key"] = env["object_key"]

    updateKubeConfig(env["kubectl_config"] if "kubectl_config" in env else "")
    warnVpnConfig(env["private_dns_address"] if target == "az" else "")

    # Don't return until all nodes and K8S system pods are ready
    announce("Waiting for nodes to come online")
    runStdout(f"{kube} wait --for=condition=Ready {timeout} --all "
            "nodes".split())
    print("All nodes online")
    announce("Waiting for K8S system pods to come online")
    cmd = "{k} wait {v} --namespace=kube-system --for=condition=Ready " \
            "{t} pods --all"
    try:
        runStdout(cmd.format(k = kube, v = "", t = timeout).split())
    except CalledProcessError as e:
        print("Timeout waiting for system pods. 2nd & final attempt.")
        # run again with verbose output
        runStdout(cmd.format(k = kube, v = "--v=2", t = timeout).split())
    print("All K8S system pods online")
    return env

def stopPortForward():
    for p in psutil.process_iter(["cmdline"]):
        c = p.info["cmdline"]
        if c and c[0] == "socat":
            port = ((c[1]).split(',')[0]).split(':')[1]
            p.terminate()
            announce("Terminated process {pid} which was port-forwarding "
                    "localhost:{port}".format(port = port, pid = p.pid))

def startPortForward():
    stopPortForward()
    announce("Waiting for pods to be ready")
    runStdout(f"{kubens} wait --for=condition=Ready pods --all "
            f"{timeout}".split())
    announce("Waiting for services to be available")
    runStdout(f"{kubens} wait --for=condition=Available deployments.apps "
            f"--all {timeout}".split())

    #
    # Get the DNS name of the load balancers we've created
    #
    lbs = {}
    ksvcs = json.loads(runCollect(f"{kubens} get services --output=json".split()
        + list(svcports.keys())))

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
    assert len(lbs) == len(svcports)

    subprocs = []
    for svc, port in svcports.items():
        sproc = subprocess.Popen("socat TCP-LISTEN:{p},fork,reuseaddr "
                "TCP:{lb}:{p}".format(p = port, lb = lbs[svc]).split(), stderr =
                subprocess.STDOUT, stdout = subprocess.DEVNULL)
        subprocs.append(sproc)
        announce("PID {pid} is now port-forwarding from localhost:{p} to "
                "{lb}:{p}".format(p = str(port), lb = lbs[svc], pid =
                    sproc.pid))

    assert len(subprocs) == len(svcports)

def retry(f, maxretries: int, err: str) -> requests.Response:
    retries = 0
    stime = 1
    while True:
        try:
            r = f()
            if r.status_code == 503:
                time.sleep(0.1)
                continue
            return r
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect: \"{err}\"; retries={retries}; sleep={stime}")
            if retries > maxretries:
                print(f"{maxretries} retries exceeded!")
                raise
            time.sleep(stime)
            retries += 1
            stime <<= 1

class ApiError(Exception):
    pass

def issuePrestoCommand(command: str, verbose = False) -> list:
    httpmaxretries = 5
    if verbose: announceSqlStart(command)
    url = "http://localhost:{}/v1/statement".format(svcports["presto"])
    headers = { "X-Presto-User": "presto_service" }
    r = retry(lambda: requests.post(url, headers = headers, data = command),
            maxretries = httpmaxretries, err = f"POST [{command}]")

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
        r = retry(lambda: requests.get(j["nextUri"], headers = headers),
                maxretries = httpmaxretries, err = f"GET nextUri [{command}]")

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

def eraseBucketContents():
    # Delete everything in the S3 bucket
    assert target in clouds
    env = getOutputVars()
    cmd = None
    if target == "aws":
        cmd = "aws s3 rm s3://{b}/{d} --recursive".format(b = bucket, d =
                dbschema)
    elif target == "az" and "adls_access_key" in env:
        cmd = ("az storage fs directory delete -y --file-system {b} "
                "--account-name {s} --account-key {a} --name /{d}").format(b =
                        bucket, s = storageacct, a = env["adls_access_key"], d =
                        dbschema)
    elif target == "gcp" and "object_address" in env:
        cmd = "gsutil rm -rf {b}/{d}".format(b = env["object_address"], d =
                dbschema)

    if cmd != None:
        announce(f"Deleting contents of bucket {bucket}")
        try:
            runStdout(cmd.split())
        except CalledProcessError as e:
            print(f"Unable to erase bucket {bucket} (already empty?)")

def loadDatabases(hive_location):
    if target == "aws":
        hive_location = f"s3://{bucket}"
    elif target == "az":
        hive_location = f"abfs://{bucket}@{hive_location}/"

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

def helmGetReleases() -> list:
    releases = []
    try:
        releases = helmGet(f"{helmns} ls --short").splitlines()
    except CalledProcessError as e:
        print("No helm releases found.")
    return releases

def helmIsReleaseInstalled(module: str) -> bool:
    return releases[module] in helmGetReleases()

def helmInstallRelease(module: str, env = {}) -> bool:
    env.update(myvars)
    env.update({
        "BucketName":        bucket,
        "DBName":            dbschema,
        "DBNameEventLogger": dbevtlog,
        "DBPassword":        dbpwd,
        "StorageAccount":    storageacct,
        "mysql_port":        dbports["mysql"],
        "postgres_port":     dbports["postgres"],
        "target":            target
        })

    # Parameterise the yaml file that configures the helm chart install
    changed, yamltmp = parameteriseTemplate(templates[module], tmpdir, env)

    if not helmIsReleaseInstalled(module):
        announce("Installing release {} using helm".format(releases[module]))
        helm("{h} install {r} {c} -f {y} --version {v}".format(h = helmns, r =
            releases[module], c = charts[module], y = yamltmp, v =
            chartversion))
        return True # freshly installed

    if not changed:
        print("Values file for {r} unchanged ➼ avoiding helm upgrade".format(r =
            releases[module]))
        return False

    announce("Upgrading release {} using helm".format(releases[module]))
    helm("{h} upgrade {r} {c} -i -f {y} --version {v}".format(h = helmns, r =
        releases[module], c = charts[module], y = yamltmp, v = chartversion))
    return False # upgraded, rather than newly installed

def helmUninstallRelease(release: str) -> None:
    helm(f"{helmns} uninstall {release} {timeout}")

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
    cpu["ranger_admin"] = cpu["ranger_db"] = cpu["hive"] = cpu["hive_db"] = c >> 4
    mem["ranger_admin"] = mem["ranger_db"] = mem["hive"] = mem["hive_db"] = m >> 4
    assert cpu["worker"] + cpu["hive"] + cpu["hive_db"] <= c
    assert mem["worker"] + mem["hive"] + mem["hive_db"] <= m
    assert cpu["worker"] + cpu["ranger_admin"] + cpu["ranger_db"] <= c
    assert mem["worker"] + mem["ranger_admin"] + mem["ranger_db"] <= m
    print("Hive gets {c}m CPU and {m}Mi mem".format(c = cpu["hive"] +
        cpu["hive_db"], m = (mem["hive"] + mem["hive_db"]) >> 10))
    print("Ranger gets {c}m CPU and {m}Mi mem".format(c = cpu["ranger_admin"] +
        cpu["ranger_db"], m = (mem["ranger_admin"] + mem["ranger_db"]) >> 10))
    env = {f"{k}_cpu": f"{v}m" for k, v in cpu.items()}
    env.update({f"{k}_mem": "{m}Mi".format(m = v >> 10) for k, v in mem.items()})
    assert nodeCount >= minnodes
    env["workerCount"] = nodeCount - 1
    return env

def helmInstallAll(env):
    helmCreateNamespace()
    installSecret(repo, licensef)

    # For GCP, we'll need to store the secret for our GCS access in K8S
    if target == "gcp":
        installSecret(gcskeyname, gcskeyfile)
        env["gcskeyname"] = gcskeyname
        env["gskeyfbn"] = gcskeyfbn

    ensureHelmRepoSetUp(repo)
    capacities = planWorkerSize()
    env.update(capacities)
    installed = False
    for module in modules:
        installed = helmInstallRelease(module, env) or installed
    # If we've installed Hive for the first time, then it will have set up fresh
    # the internal PostgreSQL DB used for metadata, which means there also
    # shouldn't be any files in our filesystem, in order to be in sync. Do this
    # to avoid errors about finding existing files.
    if installed:
        eraseBucketContents()

def helmUninstallAll():
    announce("Uninstalling all helm releases")
    for release in helmGetReleases():
        try:
            helmUninstallRelease(release)
        except CalledProcessError as e:
            print(f"Unable to uninstall release {release}: {e}")
    helmDeleteNamespace()

def awsGetCreds():
    awsAccess = runCollect("aws configure get aws_access_key_id".split())
    awsSecret = runCollect("aws configure get aws_secret_access_key".split())
    return dict(AWSAccessKey=awsAccess, AWSSecretKey=awsSecret)

def announceReady(env: dict) -> list:
    w = ["Bastion: {b}".format(b = env["bastion_address"])]
    for service, port in svcports.items():
        w.append(f"{service}: localhost:{port}")
    return w

def svcStart(skipClusterStart: bool = False) -> None:
    # First see if there isn't a cluster created yet, and create the cluster.
    # This can take a long time. This will create the control plane and workers.
    env = ensureClusterIsStarted(skipClusterStart)
    env["Region"] = region
    env.update(awsGetCreds())
    helmInstallAll(env)
    startPortForward()
    loadDatabases(env["object_address"])
    return announceReady(env)

def svcStop(emptyNodes: bool = False) -> None:
    stopPortForward()
    t = time.time()
    helmUninstallAll()
    eraseBucketContents()
    announce("nodes emptied in " + time.strftime("%Hh%Mm%Ss",
        time.gmtime(time.time() - t)))
    if emptyNodes: return

    announce(f"Ensuring cluster {clustname} is deleted")
    t = time.time()
    runTry(f"{tf} state rm module.eks.kubernetes_config_map.aws_auth".split())
    runStdout(f"{tf} destroy -auto-approve".split())
    announce("tf destroy completed in " + time.strftime("%Hh%Mm%Ss",
        time.gmtime(time.time() - t)))

def getClusterState() -> tuple:
    r = runTry(f"{tf} plan -input=false "
            "-detailed-exitcode".split()).returncode
    if r == 0:
        env = getOutputVars()
        w = ["Bastion: {b}".format(b = env["bastion_address"])]
        return True, w
    return False, []

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

def announceSummary() -> None:
    if target == "aws":
        cloud = "Amazon Web Services"
    elif target == "az":
        cloud = "Microsoft Azure"
    else:
        cloud = "Google Cloud Services"
    announceLoud([f"Cloud: {cloud}",
        f"Region: {region}",
        f"Cluster: {nodeCount} × {instanceType}"])

#
# Start of execution. Handle commandline args.
#

p = argparse.ArgumentParser(description=
        f"""Create your own Starbust demo service in AWS, Azure or GCP, starting
        from nothing. It's zero to demo in 20 minutes or less. You provide the
        instance ID of your VPN in {myvarsbf}, your desired CIDR and some other
        parameters. This script uses terraform to set up a K8S cluster, with its
        own VPC/VNet and K8S cluster, routes and peering connections, security,
        etc. Presto is automatically set up and multiple databases and a data
        lake are set up. It's designed to allow you to control the new setup
        from your laptop, without necessarily using a bastion server—although a
        bastion server is also provided as a convenience. The event logger is
        set up as well as Starburst Insights (running on a PostgreSQL
        database).""")

p.add_argument('-c', '--skip-cluster-start', action="store_true",
        help="Skip checking to see if cluster needs to be started")
p.add_argument('-e', '--empty-nodes', action="store_true",
        help="Unload k8s cluster only. Used with stop or restart.")
p.add_argument('command',
        choices = ["start", "stop", "restart", "status", "pfstart", "pfstop"],
        help="""Command to issue for demo services.
           start/stop/restart: Start/stop/restart the demo environment.
           status: Show whether the demo environment is running or not.
           pfstart: Start port-forwarding from local ports to container ports
                    (happens with start).
           pfstop: Stop port-forwarding from local ports to container ports.""")

ns = p.parse_args()
emptyNodes = ns.empty_nodes
command = ns.command

if emptyNodes and command not in ("stop", "restart"):
    p.error("-e, --empty-nodes is only used with stop and restart")

checkCLISetup()
checkRSAKey()

if command == "pfstart":
    startPortForward()
    sys.exit(0)

if command == "pfstop":
    stopPortForward()
    sys.exit(0)

announceSummary()

w = []
started = False

if command in ("stop", "restart"):
    svcStop(emptyNodes)

if command in ("start", "restart"):
    w = svcStart(ns.skip_cluster_start)
    started = True

if command == "status":
    started, w = getClusterState()

y = ["Service is " + ("started" if started else "stopped")]
if len(w) > 0:
    y += w
announceBox(f"Your {rsaPub} public key has been installed into the bastion "
        "server, so you can ssh there now (user 'ubuntu').")
announceLoud(y)
