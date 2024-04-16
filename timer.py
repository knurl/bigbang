import time
import out

class Timer:
    def __init__(self, descr: str):
        self.start = time.time()
        self.descr = descr

    def __enter__(self):
        out.announceStart(self.descr)
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.interval = self.end - self.start
        out.announceEnd(self.descr, self.interval)
