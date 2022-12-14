import io, os

def myDir():
    return os.path.dirname(os.path.abspath(__file__))
def where(leaf):
    return os.path.join(myDir(), leaf)
def readableFile(p) -> bool:
    return os.path.isfile(p) and os.access(p, os.R_OK)
def readableDir(p) -> bool:
    return os.path.isdir(p) and os.access(p, os.R_OK | os.X_OK)
def writeableDir(p) -> bool: 
    return readableDir(p) and os.access(p, os.W_OK)
