import io, os

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
