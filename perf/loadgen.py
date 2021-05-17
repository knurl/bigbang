#!python

import prestodb, time, threading
import time

# Change this array to include the queries you want to rotate through
queries = [
        "select max(nationkey) from hive.fdd.nation",
        "select max(custkey) from hive.fdd.customer",
        "select max(orderkey) from hive.fdd.orders",
        "select max(partkey) from hive.fdd.lineitem",
        "select n.name, sum(l.extendedprice) as totalprice from awsmysql.fdd.customer as c inner join azhive.fdd.orders as o on c.custkey = o.custkey inner join awshive.fdd.lineitem as l on o.orderkey = l.orderkey inner join azpostgresql.fdd.nation as n on c.nationkey = n.nationkey inner join awspostgresql.fdd.region as r on r.regionkey = n.regionkey inner join awshive.fdd.part as p on l.partkey = p.partkey where n.name in ('PERU', 'MOROCCO', 'RUSSIA') group by n.name, totalprice order by totalprice desc"
        ]
threadpoolsize = 50
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
            auth        = prestodb.auth.BasicAuthentication("presto_service", "test"),
            host        = 'presto.az.starburstdata.net',
            port        = 8445,
            catalog     = 'hive',
            schema      = 'fdd')
    cur = conn.cursor()
    q = 0
    while True:
        nq.inc()
        cur.execute(queries[q & 3])
        q += 1
        cur.fetchall()
        nq.dec()
        time.sleep(newquerypause)

threads = []
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
