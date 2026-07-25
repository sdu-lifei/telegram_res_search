#!/usr/bin/env python3
import sqlite3

database = sqlite3.connect("/opt/telegram-res-search/pansou.db")
print("resources", database.execute("select count(*) from resources").fetchone()[0])
print("candidates", database.execute(
    "select status, count(*) from harvest_candidates group by status order by status"
).fetchall())
print("runs", database.execute("select count(*) from harvest_runs").fetchone()[0])
print("latest", database.execute(
    "select discovered, confirmed_valid, inserted, invalid, deferred, errors, resource_total "
    "from harvest_runs order by id desc limit 1"
).fetchone())
