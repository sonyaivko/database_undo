"""
Measures storage ratio (box vs naive) for a single box, across a range of
leaf/cluster sizes

Usage: python3 leaf_size_sweep.py
"""
import csv
import json
import psycopg2
from psycopg2.extras import execute_values

from undo_lib import log_insertion, undo_insertion
from naive_lib import naive_log_insertion, naive_storage_bytes
from tpcc_rows import make_customer_row

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")
PK_COLS = ["c_w_id", "c_d_id", "c_id"]
W_ID, D_ID = 1, 50
SIZES = [5, 10, 15, 20, 23, 25, 30, 40, 50, 75, 100]


def setup_district(conn):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM DISTRICT WHERE d_id=%s AND d_w_id=%s", (D_ID, W_ID))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO DISTRICT VALUES (%s,%s,'D_leaf','x','x','x','MA','000011111',0.05,30000.0,3001)",
            (D_ID, W_ID))
        conn.commit()
    cur.execute("DELETE FROM CUSTOMER WHERE c_w_id=%s AND c_d_id=%s", (W_ID, D_ID))
    conn.commit()
    cur.close()


def insert_rows(conn, rows):
    cur = conn.cursor()
    cols = list(rows[0].keys())
    execute_values(cur, f"INSERT INTO CUSTOMER ({','.join(cols)}) VALUES %s",
                    [[r[c] for c in cols] for r in rows], page_size=200)
    conn.commit()
    cur.close()


if __name__ == "__main__":
    conn = psycopg2.connect(**CONN_PARAMS)
    setup_district(conn)

    results = []
    offset = 1
    for size in SIZES:
        rows = [make_customer_row(cid, D_ID, W_ID) for cid in range(offset, offset + size)]
        insert_rows(conn, rows)

        boxes, exceptions = log_insertion(conn, "customer", rows, PK_COLS)
        box_bytes = len(json.dumps(boxes, default=str))
        naive_bytes = naive_storage_bytes(naive_log_insertion(rows, PK_COLS))
        undo_insertion(conn, "customer", boxes, exceptions, PK_COLS)

        ratio = box_bytes / naive_bytes if len(boxes) == 1 else None
        print(f"size={size:4d}  boxes={len(boxes)} exc={len(exceptions)}  "
              f"box_bytes={box_bytes}  naive_bytes={naive_bytes}  "
              f"ratio={f'{ratio:.3f}x' if ratio else 'N/A (below numDims threshold)'}")
        results.append(dict(size=size, box_bytes=box_bytes, naive_bytes=naive_bytes,
                             n_boxes=len(boxes), n_exceptions=len(exceptions)))
        offset += size

    conn.close()

    with open("leaf_size_sweep.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote leaf_size_sweep.csv")