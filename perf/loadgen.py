#! /usr/bin/env python

import prestodb # type: ignore
import time, threading

# Change this array to include the queries you want to rotate through
queries = [ "select max(nationkey) from s3.s.nation",
        "select min(partkey) from s3.s.part",
        "select min(custkey) from s3.s.customer",
        "select max(orderkey) from s3.s.orders"]

threadpoolsize = 200
newconnectionpause = 0.1
newquerypause = 0.0
reportingpause = 1.0

lock = threading.Lock()

class Counter:
    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()

    def inc(self):
        with lock:
            self.count += 1

    def dec(self):
        with lock:
            self.count -= 1

    def getCount(self):
        with lock:
            return self.count

nq = Counter()

def runme():
    conn = prestodb.dbapi.connect(
            http_scheme = 'https',
            auth        = prestodb.auth.BasicAuthentication("starburst_service", "test"),
            host        = 'starburst.az.starburstdata.net',
            port        = 8443,
            catalog     = 's3',
            schema      = 's')
    cur = conn.cursor()
    q = 0
    while True:
        nq.inc()
        cur.execute(queries[q & 3])
        q += 1
        cur.fetchall()
        nq.dec()
        time.sleep(newquerypause)

threads: list[threading.Thread] = []
last = time.time()
while True:
    if len(threads) < threadpoolsize:
        t = threading.Thread(target = runme)
        t.start()
        threads.append(t)
    time.sleep(newconnectionpause)
    if (now := time.time()) - last > reportingpause:
        last = now
        print("Threads: {a}; Active queries: {q}".format(a = len(threads), q =
            nq.getCount()))
