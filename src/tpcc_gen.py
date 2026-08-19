"""
TPC-C-shaped data generator for the undo-mechanism experiments.

- Only use realistic INSERT batches shaped like TPC-C rows 

"""
import random
import string
import datetime
import psycopg2 # for DB connection 

from tpcc_rows import rand_str, rand_zip, make_customer_row

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")

random.seed(42)  # reproducible runs -- unseed later if you want variance across repeats

# generate tuples according to tpc-c schema 

def gen_warehouses(n):
    rows = []
    for w_id in range(1, n + 1):
        rows.append((
            w_id, f"WH{w_id}", rand_str(16), rand_str(16),
            rand_str(16), "MA", rand_zip(),
            round(random.uniform(0.0, 0.2), 4), 300000.0,
        ))
    return rows


def gen_districts(n_warehouses, districts_per_wh=10):
    rows = []
    for w_id in range(1, n_warehouses + 1):
        for d_id in range(1, districts_per_wh + 1):
            rows.append((
                d_id, w_id, f"D{w_id}_{d_id}", rand_str(16), rand_str(16),
                rand_str(16), "MA", rand_zip(),
                round(random.uniform(0.0, 0.2), 4), 30000.0, 3001,
            ))
    return rows


def gen_items(n):
    rows = []
    for i_id in range(1, n + 1):
        rows.append((
            i_id, random.randint(1, 10000), rand_str(24),
            round(random.uniform(1.0, 100.0), 2), rand_str(50),
        ))
    return rows

# returns a list of dicts 
def gen_customers(n_warehouses, districts_per_wh, customers_per_district):
    rows = []
    for w_id in range(1, n_warehouses + 1):
        for d_id in range(1, districts_per_wh + 1):
            for c_id in range(1, customers_per_district + 1):
                rows.append(make_customer_row(c_id, d_id, w_id))
    return rows

# helper for bulk-inserting tuples
def load(conn, table, rows, cols=None):
    if not rows:
        return
    cur = conn.cursor()

    if isinstance(rows[0], dict):
        cols = list(rows[0].keys())
        values = [[r[c] for c in cols] for r in rows]
    else:
        values = rows
    col_clause = f"({','.join(cols)})" if cols else ""
    cur.execute(f"SET client_min_messages TO WARNING")
    from psycopg2.extras import execute_values
    sql = f"INSERT INTO {table} {col_clause} VALUES %s"
    execute_values(cur, sql, rows, page_size=500)
    conn.commit()
    cur.close()

# populates the schema. only 4/9 tables

if __name__ == "__main__":
    conn = psycopg2.connect(**CONN_PARAMS)

    N_WAREHOUSES = 2
    DISTRICTS_PER_WH = 10
    CUSTOMERS_PER_DISTRICT = 300  # small slice of the real 3000

    print("Generating + loading WAREHOUSE...")
    load(conn, "WAREHOUSE", gen_warehouses(N_WAREHOUSES))

    print("Generating + loading DISTRICT...")
    load(conn, "DISTRICT", gen_districts(N_WAREHOUSES, DISTRICTS_PER_WH))

    print("Generating + loading ITEM...")
    load(conn, "ITEM", gen_items(1000))

    print("Generating + loading CUSTOMER...")
    load(conn, "CUSTOMER", gen_customers(N_WAREHOUSES, DISTRICTS_PER_WH, CUSTOMERS_PER_DISTRICT))

    cur = conn.cursor()
    for t in ["WAREHOUSE", "DISTRICT", "ITEM", "CUSTOMER"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(t, cur.fetchone()[0])
    conn.close()
