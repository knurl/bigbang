import os, sys, subprocess, threading, re
from abc import ABC, abstractmethod
from typing import Optional
import run, bbio

awsdir         = os.path.expanduser("~/.aws")
awsconfig      = os.path.expanduser("~/.aws/config")
awscreds       = os.path.expanduser("~/.aws/credentials")

okta_re = re.compile('^\[(\d)\] Okta')

def renew_creds_now() -> None:
    cmd = 'gimme-aws-creds -m'
    with subprocess.Popen(cmd.split(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True) as proc:
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ''):
            m = okta_re.match(line)
            if m:
                response = m.group(1)
                proc.communicate(input=f'{response}')
                return

def renew_creds_async():
    t = threading.Thread(target=renew_creds_now, args=())
    t.start()
    return t

def renew_creds_sync() -> None:
    t = renew_creds_async()
    t.join()

class Creds(ABC):
    def __init__(self, accesskey: str, secret: str):
        self.accesskey = accesskey
        self.secret = secret
        super().__init__()
        pass

    @abstractmethod
    def getAccessKeyName(self) -> str:
        pass

    @abstractmethod
    def getSecretName(self) -> str:
        pass

    @abstractmethod
    def toDict(self) -> dict[str, str]:
        return { self.getAccessKeyName(): self.accesskey,
                 self.getSecretName(): self.secret }

class AwsCreds(Creds):
    def isTokenFresh(self, awsAccess: str) -> bool:
        r = run.runTry("aws sts get-access-key-info --access-key-id".split() +
                [awsAccess])
        rc = r.returncode
        assert rc != 253, "Shouldn't happen. I just checked creds files?"
        if rc not in (0, 254):
            sys.exit(f"Unknown error {rc} trying to get credentials.")
        return rc == 0

    def __init__(self):
        # First make sure we can find the credentials files
        badAws = False
        if not bbio.writeableDir(awsdir):
            badAws = True
            err = f"Directory {awsdir} doesn't exist or has bad permissions."
        elif not bbio.readableFile(awsconfig):
            badAws = True
            err = f"File {awsconfig} doesn't exist or isn't readable."
        elif not bbio.readableFile(awscreds):
            badAws = True
            err = f"File {awscreds} doesn't exist or isn't readable."
        if badAws:
            print(err)
            sys.exit("Have you run aws configure?")
        awsAccess = run.runCollect("aws configure get "
                "aws_access_key_id".split())
        awsSecret = run.runCollect("aws configure get "
                "aws_secret_access_key".split())

        # Next, ensure that if we are using an access token, it remains valid
        if not self.isTokenFresh(awsAccess):
            print('Need to refresh your AWS access token. Check your phone.')
            renew_creds_sync()
            if not self.isTokenFresh(awsAccess):
                sys.exit("Unable to refresh access token.")
        super().__init__(awsAccess, awsSecret)

    def getAccessKeyName(self) -> str:
        return "AWSAccessKey"

    def getSecretName(self) -> str:
        return "AWSSecretKey"

    def toDict(self) -> dict[str, str]:
        return super().toDict()

def getCreds(target: str) -> Optional[Creds]:
    creds: Optional[Creds] = None
    if target == "aws":
        creds = AwsCreds()
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
    return creds

