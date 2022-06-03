import os, sys, pdb, requests, time, threading, io
from out import *

class ApiError(Exception):
    pass

def retryHttp(f, maxretries: int, descr: str) -> requests.Response:
    retries = 0
    stime = 1
    while True:
        try:
            r = f()
            if r.status_code == 503:
                time.sleep(0.5)
                continue
            # All good -- we exit here.
            if retries > 0:
                print(f"Succeeded on \"{descr}\" after {retries} retries")
            return r
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect: \"{descr}\"; retries={retries}; "
                    f"sleep={stime}")
            if retries > maxretries:
                print(f"{maxretries} retries exceeded!")
                raise
            time.sleep(stime)
            retries += 1
            stime <<= 1

def sendSql(url: str, ssl: bool, user: str, pwd: str, command: str,
        verbose = False) -> list:
    httpmaxretries = 10
    if verbose: announceSqlStart(command)
    hdr = { "X-Trino-User": user, "X-Trino-Source": "bigbang" }
    authtype = None
    if ssl:
        authtype = requests.auth.HTTPBasicAuth(user, pwd)
    f = lambda: requests.post(url, headers = hdr, auth = authtype, data =
            command, verify = None)
    r = retryHttp(f, maxretries = httpmaxretries, descr = f"POST [{command}]")

    data = []
    while True:
        r.raise_for_status()
        assert r.status_code == 200
        j = r.json()
        if "data" in j:
            data += j["data"]
        if "nextUri" not in j:
            if "error" in j:
                raise ApiError("Error executing SQL '{s}': error {e}".format(s
                    = command, e = str(j["error"])))
            if verbose: announceSqlEnd(command)
            return data # the only way out is success, or an exception
        f = lambda: requests.get(j["nextUri"], headers = hdr, verify = None)
        r = retryHttp(f, maxretries = httpmaxretries,
                descr = f"GET nextUri [{command}]")

