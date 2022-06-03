# bigbang-specific
import sql, cmdgrp
from out import *

# other
import os, sys, pdb, requests, time, threading, io
from typing import Any, Set, List

tpchcat  = "tpch"
tpcdscat = "tpcds"
tpccats  = {tpchcat, tpcdscat}

tpcds_queries = { 'q01.sql', 'q02.sql', 'q03.sql', 'q04.sql', 'q05.sql',
        'q06.sql', 'q07.sql', 'q08.sql', 'q09.sql', 'q10.sql', 'q11.sql',
        'q12.sql', 'q13.sql', 'q14_1.sql', 'q14_2.sql', 'q15.sql', 'q16.sql',
        'q17.sql', 'q18.sql', 'q19.sql', 'q20.sql', 'q21.sql', 'q22.sql',
        'q23_1.sql', 'q23_2.sql', 'q24_1.sql', 'q24_2.sql', 'q25.sql',
        'q26.sql', 'q27.sql', 'q28.sql', 'q29.sql', 'q30.sql', 'q31.sql',
        'q32.sql', 'q33.sql', 'q34.sql', 'q35.sql', 'q36.sql', 'q37.sql',
        'q38.sql', 'q39_1.sql', 'q39_2.sql', 'q40.sql', 'q41.sql', 'q42.sql',
        'q43.sql', 'q44.sql', 'q45.sql', 'q46.sql', 'q47.sql', 'q48.sql',
        'q49.sql', 'q50.sql', 'q51.sql', 'q52.sql', 'q53.sql', 'q54.sql',
        'q55.sql', 'q56.sql', 'q57.sql', 'q58.sql', 'q59.sql', 'q60.sql',
        'q61.sql', 'q62.sql', 'q63.sql', 'q64.sql', 'q65.sql', 'q66.sql',
        'q67.sql', 'q68.sql', 'q69.sql', 'q70.sql', 'q71.sql', 'q72.sql',
        'q73.sql', 'q74.sql', 'q75.sql', 'q76.sql', 'q77.sql', 'q78.sql',
        'q79.sql', 'q80.sql', 'q81.sql', 'q82.sql', 'q83.sql', 'q84.sql',
        'q85.sql', 'q86.sql', 'q87.sql', 'q88.sql', 'q89.sql', 'q90.sql',
        'q91.sql', 'q92.sql', 'q93.sql', 'q94.sql', 'q95.sql', 'q96.sql',
        'q97.sql', 'q98.sql', 'q99.sql' }

class ScaleSets:
    ss_list: List[str] = [
            "tiny",
            "sf1",
            "sf10",
            "sf100",
            "sf200",
            "sf400"
            ]

    def smallest(self) -> str:
        return self.ss_list[0]

    def largest(self) -> str:
        return self.ss_list[-1]

    def atscale(self, scale: int):
        return self.ss_list[self.ss_list.index('sf' + str(scale))]

    def range(self, first: str, last: str) -> set[str]:
        begin = self.ss_list.index(first)
        end = self.ss_list.index(last) + 1
        return set(self.ss_list[begin:end])

scale_sets = ScaleSets()

class TpcCatInfo:
    table_names: Set[str] = {'customer', 'inventory', 'reason',
            'ship_mode', 'store', 'item', 'store_returns', 'web_returns',
            'promotion', 'catalog_page', 'household_demographics',
            'customer_address', 'income_band', 'time_dim', 'catalog_returns',
            'catalog_sales', 'customer_demographics', 'warehouse', 'date_dim',
            'store_sales', 'web_site', 'web_page', 'web_sales', 'call_center'}

    scale_sets: dict[str, dict[str, int]] = {
            'tiny': {
                'store': 2, 'customer': 1000, 'household_demographics': 7200,
                'reason': 1, 'call_center': 2, 'web_page': 2, 'web_site': 2,
                'time_dim': 86400, 'customer_address': 1000, 'ship_mode': 20,
                'web_sales': 11876, 'warehouse': 1, 'inventory': 261261,
                'web_returns': 1152, 'item': 2000, 'catalog_page': 11718,
                'promotion': 3, 'store_returns': 11925, 'catalog_returns':
                8923, 'income_band': 20, 'customer_demographics': 1920800,
                'date_dim': 73049, 'catalog_sales': 89807, 'store_sales':
                120527
                },
            'sf1': {
                'ship_mode': 20, 'reason': 35, 'promotion': 300, 'item': 18000,
                'call_center': 6, 'time_dim': 86400, 'store': 12, 'warehouse':
                5, 'household_demographics': 7200, 'date_dim': 73049,
                'web_page': 60, 'catalog_page': 11718, 'web_site': 30,
                'customer_address': 50000, 'income_band': 20, 'customer':
                100000, 'customer_demographics': 1920800, 'web_returns': 71763,
                'inventory': 11745000, 'catalog_returns': 144067,
                'store_returns': 287514, 'web_sales': 719384, 'catalog_sales':
                1441548, 'store_sales': 2880404
                },
            'sf10': {
                'customer_address': 250000, 'web_page': 200,
                'household_demographics': 7200, 'ship_mode': 20, 'call_center':
                24, 'income_band': 20, 'promotion': 500, 'catalog_page': 12000,
                'web_site': 42, 'reason': 45, 'store': 102, 'time_dim': 86400,
                'warehouse': 10, 'date_dim': 73049, 'item': 102000,
                'customer_demographics': 1920800, 'catalog_returns': 1439749,
                'store_returns': 2875432, 'customer': 500000, 'inventory':
                133110000, 'web_returns': 719217, 'catalog_sales': 14401261,
                'store_sales': 28800991, 'web_sales': 7197566
                },
            'sf100': {
                'web_page': 2040, 'web_site': 24, 'time_dim': 86400,
                'household_demographics': 7200, 'reason': 55, 'ship_mode': 20,
                'store': 402, 'catalog_page': 20400, 'promotion': 1000,
                'call_center': 30, 'income_band': 20, 'warehouse': 15,
                'customer_address': 1000000, 'date_dim': 73049,
                'customer_demographics': 1920800, 'customer': 2000000, 'item':
                204000, 'web_returns': 7197670, 'inventory': 399330000,
                'catalog_returns': 14404374, 'store_returns': 28795080,
                'web_sales': 72001237, 'catalog_sales': 143997065,
                'store_sales': 287997024
                },
            'sf200': {
                'promotion': 450, 'ship_mode': 20, 'time_dim': 86400,
                'web_page': 342, 'reason': 37, 'income_band': 20, 'web_site':
                38, 'call_center': 8, 'catalog_page': 11718,
                'household_demographics': 7200, 'store': 212, 'warehouse': 6,
                'item': 48000, 'customer_demographics': 1920800, 'date_dim':
                73049, 'customer': 1600000, 'inventory': 37584000,
                'customer_address': 800000, 'web_returns': 14398467,
                'catalog_returns': 28798881, 'store_returns': 57591150,
                'web_sales': 144002668, 'catalog_sales': 287989836,
                'store_sales': 575995635
                },
            'sf400': {
                'web_site': 30, 'reason': 35, 'income_band': 20, 'store': 40,
                'warehouse': 5, 'household_demographics': 7200, 'promotion':
                328, 'call_center': 6, 'web_page': 116, 'catalog_page': 11718,
                'time_dim': 86400, 'ship_mode': 20, 'date_dim': 73049, 'item':
                22000, 'customer_demographics': 1920800, 'customer': 1100000,
                'inventory': 14356305, 'customer_address': 550000,
                'web_returns': 28797847, 'catalog_returns': 57592999,
                'store_returns': 115194193, 'web_sales': 288007450,
                'catalog_sales': 576001697, 'store_sales': 1151988104
                }
            }

    def __init__(self,
			url: str, tls: bool, user: str, pwd: str,
            tpc_cat_name: str,
            scale_sets: set[str]):
        assert tpc_cat_name in tpccats
        self.cat_name = tpc_cat_name

        # First, get the list of table names
        #
        if not self.table_names:
            assert len(scale_sets) > 0
            announce(f"Getting {self.cat_name} table names")
            scale_set = next(iter(scale_sets))
            tabs = sql.sendSql(url, tls, user, pwd,
                    f"show tables in {self.cat_name}.{scale_set}")
            self.table_names = {t[0] for t in tabs}
            # FIXME This is a horrible hack, but right now the tpcds table
            # dbgen_version contains a column dv_create_time of type time(3),
            # which cannot be copied to Hive. So just "ignore" this table; it
            # isn't needed for the benchmark anyway.
            if self.cat_name == tpcdscat:
                self.table_names.remove('dbgen_version')

        if not self.scale_sets:
            announce("Getting {t} table sizes for {ss}".format(t =
                self.cat_name, ss = ", ".join(scale_sets)))

            # Next, fill in the sizes of each of the tables for each scale
            #
            cg = cmdgrp.CommandGroup(url, tls, user, pwd)
            for scale_set in scale_sets:
                self.scale_sets[scale_set] = {}
                b = self.scale_sets[scale_set]
                lock = threading.Lock()
                for table_name in self.table_names:
                    if table_name not in b:
                        # callback will make a closure with b[table_name],
                        # storing the results there that come back from the SQL
                        # call. We have to use an odd construction here because
                        # Python performs late-binding with closures; to force
                        # early binding we'll use a function-factory.
                        # https://tinyurl.com/4x3t2wux
                        def make_cbs(b, scale_set, table_name):
                            def cbs(stats):
                                numrows = int(stats[0][0])
                                with lock:
                                    b[table_name] = numrows
                            return cbs
                        cmd = "select count(*) from " \
                                f"{self.cat_name}.{scale_set}.{table_name}"
                        cg.addSqlCommand(cmd, callback = make_cbs(b, scale_set,
                            table_name))
            spinWait(cg.ratioDone)
            cg.waitOnAllCopies() # Should be a no-op

    def get_cat_name(self) -> str:
        return self.cat_name

    def get_table_size(self, scale_set: str, table_name: str) -> int:
        tables = self.scale_sets.get(scale_set)
        assert tables
        size = tables.get(table_name)
        assert size
        return size

    def get_table_names(self) -> Set[str]:
        return self.table_names
