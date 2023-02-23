import os, sys, pdb, requests, time, threading, io
from out import *

# Suppress info-level messages from the requests library
import logging
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

class TrinoConnection:
    def __init__(self, url: str, user: str, pwd: str):
        self.url = url
        self.user = user
        self.pwd = pwd

    class ApiError(Exception):
        pass

    class HttpPostError(Exception):
        pass

    def retry_http(self, f: Callable, maxretries: int,
                   descr: str) -> requests.Response:
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
            except requests.exceptions.Timeout as e:
                print(f"Timeout error: \"{descr}\"; retries={retries}; "
                        f"sleep={stime}")
            if retries > maxretries:
                raise self.HttpPostError(f'{maxretries} retries exceeded!')
            time.sleep(stime)
            retries += 1
            stime <<= 1

    def send_sql(self, sql_cmd: str, verbose = False) -> list[list[str]]:
        httpmaxretries = 10
        if verbose:
            announceSqlStart(sql_cmd)
        hdr = {
                "X-Trino-User": self.user,
                "X-Trino-Role": 'system=ROLE{sysadmin}',
                "X-Trino-Source": 'bigbang'
                }
        authtype = None
        ssl = self.url.startswith('https://')
        if ssl:
            authtype = requests.auth.HTTPBasicAuth(self.user, self.pwd)
        f = lambda: requests.post(self.url, headers=hdr, auth=authtype,
                                  data=sql_cmd, verify=ssl, timeout=1.5)
        r = self.retry_http(f, maxretries=httpmaxretries,
                            descr=f"POST [{sql_cmd}]")

        data = []
        while True:
            r.raise_for_status()
            assert r.status_code == 200
            j = r.json()
            if "data" in j:
                data += j["data"]
            if "nextUri" not in j:
                if "error" in j or "warning" in j:
                    raise self.ApiError("Error executing SQL '{s}': "
                                        "error {e}".format(s=sql_cmd,
                                                           e=str(j["error"])))

                if verbose:
                    announceSqlEnd(sql_cmd)
                return data # the only way out is success, or an exception
            f = lambda: requests.get(j["nextUri"], headers=hdr, verify=ssl)
            r = self.retry_http(f, maxretries=httpmaxretries,
                                descr=f"GET nextUri [{sql_cmd}]")
