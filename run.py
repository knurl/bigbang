import subprocess

#
# Some handy functions for running commands and collecting results
#
def run(args, check = True, verbose = True):
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
