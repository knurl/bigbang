import sys, subprocess, time
from subprocess import CalledProcessError
from typing import Callable, Any

#
# Some handy functions for running commands and collecting results
#
def run(args, check = True, verbose = True) -> subprocess.CompletedProcess:
    if len(args) < 1:
        sys.exit("Not enough arguments were specified to tryrun")

    command = " ".join(args)
    if verbose: print(command)

    # if the user specifies verbose, print the results to the screen as they
    # come, otherwise capture the results to an internal buffer
    return subprocess.run(args, capture_output = (not verbose), check = check,
            text = True)

# Run a command string in a shell
def runShell(cmd: str) -> int:
    return subprocess.run(cmd, shell = True, stdout = subprocess.DEVNULL,
            stderr = subprocess.STDOUT).returncode

# CheckRC==False, as we don't want to throw an exception if this fails. Just get
# the returncode and send it back, and don't print anything out.
def runTry(args) -> subprocess.CompletedProcess:
    return run(args, check = False, verbose = False)

# CheckRC==True, and we're not collecting a string, so no need to return
# anything back to calling function
def runStdout(args):
    run(args, check = True, verbose = True)

# CheckRC==True, and we are collecting output, which we'll return back
def runCollect(args) -> str:
    return run(args, check = True, verbose = False).stdout.strip()

def retryRun(f: Callable[[], subprocess.CompletedProcess], maxretries: int,
        descr: str) -> subprocess.CompletedProcess:
    retries = 0
    stime = 1
    e: Any[None, Exception] = None
    while True:
        try:
            cp: subprocess.CompletedProcess = f()

            if cp.returncode == 0:
                # All good -- we exit here.
                if retries > 0:
                    print(f"Succeeded on \"{descr}\" after {retries} retries")
                return cp
        except CalledProcessError as e0:
            e = e0
            pass

        print(f"Encountered error with \"{descr}\"; retries={retries}; "
                    "sleep={stime}")
        if retries > maxretries:
            print(f"{maxretries} retries exceeded!")
            if e != None:
                raise e
            assert cp.returncode != 0
            return cp

        time.sleep(stime)
        retries += 1
        stime <<= 1

