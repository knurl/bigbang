import sys
import subprocess
import time
from subprocess import CalledProcessError

#
# Some handy functions for running commands and collecting results
#

# if the user specifies verbose, print the results to the screen as they come,
# otherwise capture the results to an internal buffer
def run(args, check = True, verbose = True) -> subprocess.CompletedProcess:
    if len(args) < 1:
        sys.exit("Not enough arguments were specified to tryrun")

    command = " ".join(args)
    if verbose:
        print(command)

    return subprocess.run(args, capture_output=(not verbose), check=check,
                          text=True)

# Run a command string in a shell
def runShell(cmd: str) -> int:
    return subprocess.run(cmd, shell=True, executable='/bin/bash',
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.STDOUT).returncode

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

def runIgnore(args) -> None:
    run(args, check = True, verbose = False)

def retryRun(args, maxattempts: int) -> subprocess.CompletedProcess:
    attempts = 1
    stime = 1
    cmd = ' '.join(args)
    assert(maxattempts >= attempts)
    while True:
        try:
            # verbose = False, so capture stdout to cp.stdout
            cp = run(args, check = True, verbose = False)
            assert(cp.returncode == 0) # check = True ensures this
            return cp
        except CalledProcessError:
            print(f'Nonzero RC, att={attempts}, sl={stime}: [{cmd}]')
            if attempts >= maxattempts:
                print(f"{maxattempts} attempts exhausted!")

                # If we previously muted a CalldedProcessError exception, raise
                # that exception now
                raise

        time.sleep(stime)
        attempts += 1
        stime <<= 1
