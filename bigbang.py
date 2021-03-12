#!python

import os, hashlib, argparse, sys, pdb, textwrap, requests, json, yaml
import subprocess, ipaddress, glob, threading, time, concurrent.futures
from run import run, runTry, runStdout, runCollect
from subprocess import CalledProcessError
import psutil # type: ignore
import jinja2
from typing import Tuple, Iterable

def myDir():
    return os.path.dirname(os.path.abspath(__file__))
def where(leaf):
    return os.path.join(myDir(), leaf)

#
# Read the configuration yaml for _this_ Python script ("my-vars.yaml"). This
# is the main configuration file one needs to edit. There is a 2nd configuration
# file, very small, called ./helm-creds.yaml, which contains just the username
# and password for the helm repo you wish to use to get the helm charts.
#
myvarsbf = "my-vars.yaml"
myvarsf  = where("my-vars.yaml")
try:
    with open(myvarsf) as mypf:
        myvars = yaml.load(mypf, Loader = yaml.FullLoader)
except IOError as e:
    sys.exit(f"Couldn't read user variables file {e}")

try:
    email        = myvars["Email"]
    region       = myvars["Region"]
    mySubnetCidr = myvars["MyCIDR"]
    nodeCount    = myvars["NodeCount"]
    license      = myvars["LicenseName"]
    repo         = myvars["HelmRepo"]
    repoloc      = myvars["HelmRepoLocation"]
    awsvpns      = myvars["AWSVPNInstanceIDs"]
    azurevpns    = myvars["AzureVPNVnetNames"]
except KeyError as e:
    sys.exit(f"Unspecified configuration parameter {e} in {myvarsf}")

# Check the license file
licensebf = f"{license}.license"
licensef = where(licensebf)
if not (os.path.isfile(licensef) and os.access(licensef, os.R_OK)):
    sys.exit(f"Your {myvarsf} file specifies a license named {license} "
            f"located at {licensef} but no readable file exists there.")

# Verify the email looks right, and extract username from it
emailparts = email.split('@')
if not (len(emailparts) == 2 and "." in emailparts[1]):
    sys.exit(f"Email specified in {myvarsf} must be a full email address")
username = emailparts[0]
codelen = min(3, len(username))
code = username[:codelen]

if region in awsvpns:
    target = "aws"
elif region in azurevpns:
    target = "azure"
else:
    sys.exit(f"Region {region} must be added to the VPN section in {myvarsf}")

if nodeCount < 3:
    sys.exit(f"Must have at least 3 nodes; {nodeCount} set in {myvarsf}")

try:
    ipntwk = ipaddress.ip_network(mySubnetCidr)
except ValueError as e:
    print(f"It appears the 'MyCIDR' value in {myvarsf} is not in the format "
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
kubeconfig  = os.path.expanduser("~/.kube/config")
templatedir = where("templates")
tmpdir      = "/tmp"
tfvars      = "variables.tf" # basename only, no path!
svcports    = { "presto": 8080, "ranger": 6080 }
dbports     = { "mariadb": 3306, "postgres": 5432 }
tpchschema  = "tiny"
tpchcat     = "tpch"
hivecat     = "hive"
syscat      = "system"
forwarder   = where("azure/forwarderSetup.sh")
tfdir       = where(target)
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
kubens      = f"kubectl --namespace {namespace}"
azuredns    = "168.63.129.16"

for d in [templatedir, tmpdir, tfdir]:
    assert os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK | os.X_OK)

# Make a short, unique name, handy for marking created files, naming resources,
# and other purposes.
hlen = 3
s = username + region
hnum = int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 10**hlen
shortname = code + str(hnum).zfill(hlen)

clustname = shortname + "cl"
bucket = shortname + "bk"
storageacct = shortname + "sa"

templates = {}
releases = {}
charts = {}
modules = ["hive", "ranger", "presto"]
for module in modules:
    templates[module] = f"{module}_v.yaml"
    releases[module] = f"{module}-{shortname}"
    charts[module] = f"{repo}/starburst-{module}"

# Important announcements to the user!
def announce(s):
    print(f"====> {s}")

def announcePresto(s):
    print(f"SQL-> {s}")

def announceLoud(s):
    x = "====> {} <====".format(s.upper())
    b = '='*len(x)
    print(f"{b}\n{x}\n{b}")

def announceBox(s):
    boundslen = 80
    bl = "| "
    br = " |"
    textlen = boundslen - len(bl) - len(br)
    bord = '-'*boundslen
    print(bord)
    lines = textwrap.wrap(s, width = textlen, break_on_hyphens = False)
    for l in lines:
        padl = bl + l.ljust(textlen) + br
        assert len(padl) == boundslen
        print(padl)
    print(bord)

def getVpnInstanceId() -> str:
    try:
        return awsvpns[region]
    except KeyError as e:
        print(f"Region {region} not listed for AWS VPN instances in {myvarsf}")
        raise

def getVpnVnet() -> dict:
    try:
        vnet = azurevpns[region]
        return { "VpnVnetResourceGroup": vnet["resourceGroup"],
                 "VpnVnetName": vnet["name"] }
    except KeyError as e:
        print(f"Region {region} not listed for Azure VPN vnets in {myvarsf}")
        raise

def warnVpnConfig(privateDnsAddr: str = ""):
    s = textwrap.dedent(f"""\
            NB: Your VPC/VNET CIDR is listed as '{mySubnetCidr}', which must
            be added to your home workstation's routing table.""")

    ovpnfiles = glob.glob(os.path.expanduser("~/Library/Application Support/"
        "Tunnelblick/Configurations/*/Contents/Resources/config.ovpn"))
    if (l := len(ovpnfiles)) > 0:
        s += textwrap.dedent(""" \
                It looks like you're using Tunnelblick. To achieve this routing
                you could add 'route {netaddr} {netmask}' to your OpenVPN client
                config and reconnect Tunnelblick.""".format(netaddr =
                    ipntwk.network_address, netmask = ipntwk.netmask))

    if target == "azure":
        s += textwrap.dedent(""" \
                For Azure, you also will need {p} and {a} listed as DNS
                resolvers, in that order, to access the new demo
                vnet.""".format(p = privateDnsAddr, a = azuredns))

    announceBox(s)

def parameteriseTemplate(template, targetDir, varsDict):
    assert os.path.basename(template) == template, \
            f"YAML template {template} should be in basename form (no path)"
    root, ext = os.path.splitext(template)
    assert len(root) > 0 and len(ext) > 0

    # temporary file where we'll write the filled-in template
    yamltmp = f"{targetDir}/{root}-{shortname}{ext}"

    # render the template with the parameters, and capture the result
    try:
        file_loader = jinja2.FileSystemLoader(templatedir)
        env = jinja2.Environment(loader = file_loader)
        t = env.get_template(template)
        output = t.render(varsDict)
    except jinja2.TemplateNotFound as e:
        print(f"Couldn't read {template} from {templatedir} due to {e}")
        raise

    if os.path.exists(yamltmp):
        if os.path.isfile(yamltmp):
            os.remove(yamltmp)
        else:
            sys.exit("Please manually remove {yamltmp} and rerun")

    os.umask(0)
    flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL

    try:
        # some of these config files contain user credentials in plaintext, so
        # don't allow them to be read by anyone but the user
        with open(os.open(path=yamltmp, flags=flags, mode=0o600), 'w') as fh:
            fh.write(output)
    except IOError as e:
        print(f"Couldn't write config file {yamltmp} due to {e}")
        raise

    return yamltmp

def getOutputVars() -> dict:
    env = json.loads(runCollect(f"{tf} output -json".split()))
    return {k: v["value"] for k, v in env.items()}

# Azure does some funky stuff with usernames for databases: It interpose a
# gateway in front of the database that forwards connections from
# username@hostname to username at hostname (supplied separately). So we must
# supply usernames in different formats for AWS and Azure.
def generateDatabaseUsers(env: dict) -> None:
    for db in ["mariadb", "postgres", "evtlog"]:
        env[db + "_user"] = dbuser
        if target == "azure":
            env[db + "_user"] += "@" + env[db + "_address"]

def ensureClusterIsStarted(skipClusterStart: bool) -> dict:
    env = {
            "ClusterName":       clustname,
            "DBName":            dbschema,
            "DBNameEventLogger": dbevtlog,
            "DBPassword":        dbpwd,
            "DBUser":            dbuser,
            "ForwarderScript":   forwarder,
            "NodeCount":         nodeCount,
            "BucketName":        bucket,
            "StorageAccount":    storageacct,
            "ShortName":         shortname,
            "UserName":          username
            }

    env.update(myvars)
    if target == "aws":
        env["VpnInstanceId"] = getVpnInstanceId()
        env["InstanceType"] = myvars["AWSInstanceType"]
    elif target == "azure":
        env.update(getVpnVnet())
        env["InstanceType"] = myvars["AzureVMType"]
        env["BastionInstanceType"] = myvars["AzureBastionVMType"]
    parameteriseTemplate(tfvars, tfdir, env)

    if not skipClusterStart:
        announce("Establishing K8S cluster from {n} nodes of {i}".format(n =
            nodeCount, i = env["InstanceType"]))
        runStdout(f"{tf} init -input=false".split())
        t = time.time()
        runStdout(f"{tf} apply -auto-approve -input=false".split())
        announce("tf apply completed in " + time.strftime("%Hh%Mm%Ss",
            time.gmtime(time.time() - t)))

    # Get variables returned from terraform run
    env = getOutputVars()
    generateDatabaseUsers(env) # Modify dict in-place

    # Update kubectl config file
    announce(f"Updating kube config file at {kubeconfig}")
    os.makedirs(os.path.dirname(kubeconfig), mode=0o700, exist_ok=True)
    with open(kubeconfig, 'w') as k:
        k.write(env["kubectl_config"])
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
    announce("Waiting for services to be ready")
    runStdout(f"{kubens} wait --for=condition=Available --timeout=10m --all "
            "deployments".split())

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

class ApiError(Exception):
    pass

def retry(f, maxretries: int, err: str) -> requests.Response:
    retries = 0
    stime = 1
    while True:
        try:
            return f()
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect: \"{err}\"; retries={retries}; sleep={stime}")
            if retries > maxretries:
                print(f"{maxretries} retries exceeded!")
                raise
            time.sleep(stime)
            retries += 1
            stime <<= 1

def issuePrestoCommand(command: str, verbose = False) -> list:
    httpmaxretries = 5
    if verbose: announcePresto(command)
    url = "http://localhost:{}/v1/statement".format(svcports["presto"])
    headers = { "X-Presto-User": "presto_service" }
    r = retry(lambda: requests.post(url, headers = headers, data = command),
            maxretries = httpmaxretries, err = f"POST [{command}]")

    data = []
    while True:
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise ApiError("Error executing SQL '{s}': error {e}".format(s =
                command, e = str(j["error"])))
        if "data" in j:
            data += j["data"]
        if "nextUri" not in j:
            return data
        r = retry(lambda: requests.get(j["nextUri"], headers = headers),
                maxretries = httpmaxretries, err = f"GET nextUri [{command}]")

def copySchemaTables(srcCatalog: str, srcSchema: str,
        dstCatalogs: list, dstSchema: str):
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
            if dstCatalog == "hive":
                if target == "aws":
                    location = f"s3://{bucket}/{dstSchema}"
                elif target == "azure":
                    location = f"abfs://{bucket}@{storageacct}.dfs.core." \
                            f"windows.net/datasets/{dstSchema}"
                clause = f" with (location = '{location}')"
            else:
                clause = ""

            issuePrestoCommand(f"create schema {dstCatalog}.{dstSchema}" +
                    clause, verbose = True)
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
    cmd = None
    if target == "aws":
        cmd = f"aws s3 rm s3://{bucket} --recursive"
    elif target == "azure":
        env = getOutputVars()
        try:
            ak = env["adls_access_key"]
            cmd = ("az storage fs directory delete -y --file-system {b} "
                    "--account-name {s} --account-key {a} --name "
                    "/datasets/{d}").format(b = bucket, s = storageacct, a =
                            env["adls_access_key"], d = dbschema)
        except KeyError as e:
            print("Azure storage account appears to be shut down")
    else:
        return

    if cmd != None:
        announce(f"Deleting contents of bucket {bucket}")
        runTry(cmd.split())

def loadDatabases():
    # First copy from tpch to hive...
    announce(f"populating tables in {hivecat}")
    copySchemaTables(tpchcat, tpchschema, [hivecat], dbschema)

    # Then copy from hive to everywhere in parallel
    ctab = issuePrestoCommand("show catalogs")
    dstCatalogs = [c[0] for c in ctab if c[0] not in avoidcat + [hivecat]]
    announce("populating tables in {}".format(", ".join(dstCatalogs)))
    copySchemaTables(hivecat, dbschema, dstCatalogs, dbschema)

def installLicense():
    r = runTry(f"{kubens} get secrets {repo}".split())
    if r.returncode != 0: runStdout(f"{kubens} create secret generic {repo} "
                f"--from-file {license}".split())

    announce(f"license file {license} is installed as secret")

def helmTry(cmd: str) -> subprocess.CompletedProcess:
    return runTry(["helm"] + cmd.split())

def helm(cmd: str) -> None:
    runStdout(["helm"] + cmd.split())

def helmGet(cmd: str) -> str:
    return runCollect(["helm"] + cmd.split())

def ensureHelmRepoSetUp():
    if (r := helmTry("repo list -o=json")).returncode != 0:
        sys.exit("Helm not installed.")

    repos = (x["name"] for x in json.loads(r.stdout))
    if repo not in repos:
        try:
            helm(f"repo add --username {repouser} --password "
                f"{repopass} {repo} {repoloc}")
        except CalledProcessError as e:
            print("Could not install (or verify installation of) "
                    f"{repo} at {repoloc}")
            raise

    announce(f"Verified {repo} set up as helm repo")

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

def helmInstallRelease(module: str, kv = {}) -> bool:
    installed = False

    kv.update({
        "BucketName":        bucket,
        "DBName":            dbschema,
        "DBNameEventLogger": dbevtlog,
        "DBPassword":        dbpwd,
        "StorageAccount":    storageacct,
        "mariadb_port":      dbports["mariadb"],
        "postgres_port":     dbports["postgres"]
        })

    # Parameterise the yaml file that configures the helm chart install
    kv.update(myvars)
    yamltmp = parameteriseTemplate(templates[module], tmpdir, kv)

    if helmIsReleaseInstalled(module): # Upgrade
        announce("Upgrading release {} using helm".format(releases[module]))
        helm("{h} upgrade {r} {c} -i -f {y}".format(h = helmns, r =
            releases[module], c = charts[module], y = yamltmp))
    else: # Fresh install
        installed = True
        announce("Installing release {} using helm".format(releases[module]))
        helm("{h} install {r} {c} -f {y}".format(h = helmns, r =
            releases[module], c = charts[module], y = yamltmp))

    return installed

def helmUninstallRelease(release: str) -> None:
    helm(f"{helmns} uninstall {release}")

def normaliseCPU(cpu) -> int:
    if cpu.endswith("m"):
        cpu = cpu[:-1]
        assert cpu.isdigit()
        cpu = int(cpu)
    else:
        assert cpu.isdigit()
        cpu = int(cpu) * 1000
    return cpu

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

    for q in p: # for every pod
        if q["metadata"]["namespace"] == namespace:
            continue
        nodename = q["spec"]["nodeName"] # see what node it's on
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
    return mincpu, minmem

def planWorkerSize() -> dict:
    # Each worker or coordinator should get most of the CPU and memory on every
    # node. The remainder should be reserved for _either_ Ranger or Hive.
    c, m = getMinNodeResources()
    cpu = {}
    mem = {}
    cpu["worker"] = cpu["coordinator"] = (c >> 3) * 7
    mem["worker"] = mem["coordinator"] = (m >> 3) * 7
    cpu["ranger_admin"] = cpu["ranger_db"] = cpu["hive"] = cpu["hive_db"] = c >> 4
    mem["ranger_admin"] = mem["ranger_db"] = mem["hive"] = mem["hive_db"] = m >> 4
    assert cpu["worker"] + cpu["hive"] + cpu["hive_db"] <= c
    assert mem["worker"] + mem["hive"] + mem["hive_db"] <= m
    assert cpu["worker"] + cpu["ranger_admin"] + cpu["ranger_db"] <= c
    assert mem["worker"] + mem["ranger_admin"] + mem["ranger_db"] <= m
    env = {f"{k}_cpu": f"{v}m" for k, v in cpu.items()}
    env.update({f"{k}_mem": "{m}Mi".format(m = v >> 10) for k, v in mem.items()})
    assert nodeCount >= 3
    env["workerCount"] = nodeCount - 1
    return env

def helmInstallAll(kv):
    helmCreateNamespace()
    installLicense()
    ensureHelmRepoSetUp()
    env = planWorkerSize()
    env.update(kv)
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

def svcStart(skipClusterStart: bool = False) -> None:
    # First see if there isn't a cluster created yet, and create the cluster.
    # This can take a long time. This will create the control plane and workers.
    env = ensureClusterIsStarted(skipClusterStart)
    env["Region"] = region
    env.update(awsGetCreds())
    helmInstallAll(env)
    warnVpnConfig(["private_dns_address"] if target == "azure" else "")
    startPortForward()
    loadDatabases()

def svcStop(emptyNodes: bool = False) -> None:
    t = time.time()
    helmUninstallAll()
    announce("nodes emptied in " + time.strftime("%Hh%Mm%Ss",
        time.gmtime(time.time() - t)))
    eraseBucketContents()
    if emptyNodes: return

    announce(f"Ensuring cluster {clustname} is deleted")
    t = time.time()
    runTry(f"{tf} state rm module.eks.kubernetes_config_map.aws_auth".split())
    runStdout(f"{tf} destroy -auto-approve".split())
    announce("tf destroy completed in " + time.strftime("%Hh%Mm%Ss",
        time.gmtime(time.time() - t)))
    stopPortForward()

def getClusterState() -> Tuple[bool, bool]:
    started = stopped = False

    if (r := runTry(f"{tf} plan -input=false -detailed-exitcode".split())).returncode == 0:
        started = True
    elif (r := runTry(f"{tf} state list".split())).returncode == 0 and len(r.stdout) == 0:
        stopped = True

    return started, stopped

#
# Start of execution. Handle commandline args.
#
p = argparse.ArgumentParser(description=
        f"""Create your own Starbust demo service in AWS or Azure, starting from
        nothing. You provide the instance ID of your VPN in {myvarsf}, your
        desired CIDR and some other parameters. This script uses terraform to
        set up a K8S cluster, with its own VPC/VNet and K8S cluster, routes and
        peering connections, security, etc. Presto is automatically set up and
        multiple databases and a data lake are set up. It's designed to allow
        you to control the new setup from your laptop, without necessarily using
        a bastion server. The event logger is set up as well as Starburst
        Insights (running on a PostgreSQL database).""")

p.add_argument('-c', '--skip-cluster-start', action="store_true",
        help="Skip checking to see if cluster needs to be started")
p.add_argument('-e', '--empty-nodes', action="store_true",
        help="Unload k8s cluster only. Used with stop or restart.")
p.add_argument('command',
        choices = ["start", "stop", "restart", "status", "pfstart", "pfstop",
            "load"],
        help="""Command to issue for demo services.
           start/stop/restart: Start/stop/restart the demo environment.
           status: Show whether the demo environment is running or not.
           pfstart: Start port-forwarding from local ports to container ports
                    (happens with start).
           pfstop: Stop port-forwarding from local ports to container ports.
           load: Load databases with tpch data (happens with start).""")

ns = p.parse_args()
emptyNodes = ns.empty_nodes
command = ns.command

if emptyNodes and command != "stop":
    p.error("-e, --empty-nodes is only used with stop and restart")

announce(f"cloud '{target}', region '{region}'")

if command == "pfstart":
    startPortForward()
    sys.exit(0)

if command == "pfstop":
    stopPortForward()
    sys.exit(0)

if command == "load":
    startPortForward()
    loadDatabases()
    sys.exit(0)

if command in ("stop", "restart"):
    svcStop(emptyNodes)

if command in ("start", "restart"):
    svcStart(ns.skip_cluster_start)

started, stopped = getClusterState()

if started:
    announceLoud("Service is started")
elif stopped:
    announceLoud("Service is stopped")
else:
    announceLoud("Service state is undefined. Issue start or stop?")

