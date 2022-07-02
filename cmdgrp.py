# bigbang-specific
import sql, tpc

# other
import os, sys, pdb, requests, time, threading, io
import google.api_core.exceptions # type: ignore
from google.cloud import bigquery, storage # type: ignore

class CommandGroup:
    def __init__(self, url: str, ssl: bool, user: str, pwd: str):
        self.url = url
        self.ssl = ssl
        self.user = user
        self.pwd = pwd
        self.cv = threading.Condition()
        self.workToDo = 0
        self.workDone = 0

    # Methods modifying state protected by cv (condition variable) lock

    # Must be called with lock held--and this is only called by wait_for on the
    # condition variable, which always guarantees the lock is held
    def allCommandsDone(self) -> bool:
        assert self.workDone <= self.workToDo
        return self.workDone == self.workToDo

    def ratioDone(self) -> float:
        with self.cv:
            assert self.workDone <= self.workToDo, \
                    f"{self.workDone} should be <= {self.workToDo}"
            # It's possible that no commands were processed, in which case
            # avoid doing a division-by-zero by saying we're finished.
            ratio = float(self.workDone) / self.workToDo \
                    if self.workToDo > 0 else 1.0
            return ratio

    def processSqlCommand(self, cmd: str, callback = None) -> None:
        x = sql.sendSql(self.url, self.ssl, self.user, self.pwd, cmd)
        if callback:
            callback(x)
        with self.cv:
            self.workDone += 1
            self.cv.notify_all()

    def addSqlCommand(self, cmd, callback = None,
            nothread: bool = False) -> None:
        if nothread:
            self.processSqlCommand(cmd, callback)
        else:
            t = threading.Thread(target = self.processSqlCommand,
                    args = (cmd, callback, ))
        with self.cv:
            self.workToDo += 1
        if not nothread:
            t.start()

    def checkCopiedTable(self, dstCatalog: str, dstSchema: str, dstTable: str,
            rows: int) -> None:
            dest = "{dc}.{ds}.{dt}".format(dc = dstCatalog, ds = dstSchema,
                dt = dstTable)
            try:
                copiedRows = sql.sendSql(self.url, self.ssl, self.user,
                        self.pwd, f"select count(*) from {dest}")[0][0]
                if copiedRows < rows:
                    print(f"Tried to process {rows}, only did {copiedRows}")
            except sql.ApiError as e:
                print(f"Couldn't read rows from {dest}")

    def processSqlTableCommand(self, srcTable: str, dstCatalog: str,
            dstSchema: str, rows: int, cmd: str = None,
            check: bool = False) -> None:
        if cmd:
            sql.sendSql(self.url, self.ssl, self.user, self.pwd, cmd)

        if check:
            self.checkCopiedTable(dstCatalog, dstSchema, srcTable, rows)

        # We get here whether it works or not
        with self.cv:
            self.workDone += rows
            self.cv.notify_all()

    def addSqlTableCommand(self, tpcds_cat_info, tpcdsSchema: str, srcTable:
            str, dstCatalog: str, dstSchema: str, cmd: str = None,
            check: bool = False) -> None:
        rows = tpcds_cat_info.get_table_size(tpcdsSchema, srcTable)
        t = threading.Thread(target = self.processSqlTableCommand,
                args = (srcTable, dstCatalog, dstSchema, rows, cmd, check, ))
        with self.cv:
            self.workToDo += rows
        t.start()

    def processBqCommand(self, srcCatalog: str, srcSchema: str, srcTable: str,
            bqCatalog: str, dstSchema: str, rows: int, bucket: str,
            gcp_project: str, check: bool = False) -> None:
        # Get the list of files to be loaded
        storage_client = storage.Client()
        blobs = storage_client.list_blobs(bucket,
                prefix=f"{srcCatalog}/{srcSchema}/{srcTable}/")
        paths = [f"gs://{bucket}/{b.name}" for b in blobs if b.name[-1] != '/']
        assert len(paths) > 0

        # Construct a BigQuery client object.
        client = bigquery.Client()

        # TODO this could break if someone changes to Parquet format
        job_config = bigquery.LoadJobConfig(write_disposition =
            bigquery.WriteDisposition.WRITE_EMPTY, source_format =
            bigquery.SourceFormat.ORC,)

        table_id = "{dp}.{ds}.{st}".format(dp = gcp_project, ds = dstSchema,
                st = srcTable)
        try:
            load_job = client.load_table_from_uri(paths, table_id,
                    job_config=job_config)  # Make an API request.
            load_job.result()  # Waits for the job to complete.
        except google.api_core.exceptions.Conflict as e:
            # This exception indicates that there was already a table. That's
            # fine and we can completely ignore that message.
            pass
        # This check should pass even if we got a write conflict
        destination_table = client.get_table(table_id)
        assert destination_table.num_rows == rows

        if check:
            self.checkCopiedTable(bqCatalog, dstSchema, srcTable, rows)

        # We get here whether it works or not
        with self.cv:
            self.workDone += rows
            self.cv.notify_all()

    def addBqCommand(self, tpc_cat_info, tpcdsSchema: str, srcCatalog: str,
            srcSchema: str, srcTable: str, bqCatalog: str, dstSchema: str,
            bucket: str, gcp_project: str, check: bool = False) -> None:
        rows = tpc_cat_info.get_table_size(tpcdsSchema, srcTable)
        t = threading.Thread(target = self.processBqCommand,
                args = (srcCatalog, srcSchema, srcTable, bqCatalog, dstSchema,
                rows, bucket, gcp_project, check,))
        with self.cv:
            self.workToDo += rows
        t.start()

    def waitOnAllCopies(self) -> None:
        with self.cv:
            self.cv.wait_for(self.allCommandsDone)
