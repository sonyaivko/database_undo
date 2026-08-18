"""
Insertion sweep: box-based logInsertion vs naive PK-list baseline, as a function
of batch size. Uses fresh districts per trial so every box is a clean single
box.
"""
import csv
import json
import time
import psycopg2
from psycopg2.extras import execute_values

from undo_lib import log_insertion, undo_insertion
from naive_lib import naive_log_insertion, naive_storage_bytes, naive_undo_insertion
from tpcc_rows import make_customer_row

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")
PK_COLS = ["c_w_id", "c_d_id", "c_id"]

BATCH_SIZES = [10, 25, 50, 100, 250, 500, 1000, 2000]
TRIALS_PER_SIZE = 5
NEXT_DISTRICT_ID = 100  # fresh district IDs, well above TPC-C's normal 1-10 range


def ensure_district(conn, d_id, w_id=1):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM DISTRICT WHERE d_id=%s AND d_w_id=%s", (d_id, w_id))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO DISTRICT VALUES (%s,%s,%s,'x','x','x','MA','000011111',0.05,30000.0,3001)",
            (d_id, w_id, f"D{w_id}_{d_id}"))
        conn.commit()
    cur.close()


def insert_rows(conn, rows):
    cur = conn.cursor()
    cols = list(rows[0].keys())
    col_sql = ",".join(cols)
    values = [[r[c] for c in cols] for r in rows]
    execute_values(cur, f"INSERT INTO CUSTOMER ({col_sql}) VALUES %s", values, page_size=500)
    conn.commit()
    cur.close()


def run_trial(conn, batch_size, district_id):
    ensure_district(conn, district_id)
    rows = [make_customer_row(c_id, d_id=district_id, w_id=1) for c_id in range(1, batch_size + 1)]
    insert_rows(conn, rows)

    # --- box-based logging ---
    t0 = time.perf_counter()
    boxes, exceptions = log_insertion(conn, "customer", rows, PK_COLS)
    box_log_time = time.perf_counter() - t0
    box_bytes = len(json.dumps(boxes, default=str)) + len(json.dumps(exceptions))

    t0 = time.perf_counter()
    undo_insertion(conn, "customer", boxes, exceptions, PK_COLS)
    box_undo_time = time.perf_counter() - t0

    # --- naive baseline (reinsert same rows) ---
    insert_rows(conn, rows)
    t0 = time.perf_counter()
    pk_list = naive_log_insertion(rows, PK_COLS)
    naive_log_time = time.perf_counter() - t0
    naive_bytes = naive_storage_bytes(pk_list)

    t0 = time.perf_counter()
    naive_undo_insertion(conn, "customer", pk_list, PK_COLS)
    naive_undo_time = time.perf_counter() - t0

    return dict(
        batch_size=batch_size, n_boxes=len(boxes), n_exceptions=len(exceptions),
        box_log_time=box_log_time, box_undo_time=box_undo_time, box_bytes=box_bytes,
        naive_log_time=naive_log_time, naive_undo_time=naive_undo_time, naive_bytes=naive_bytes,
    )


def measure_avg_row_bytes(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT AVG(pg_column_size(c.*)) FROM {table} c")
    v = cur.fetchone()[0]
    cur.close()
    return float(v)


if __name__ == "__main__":
    conn = psycopg2.connect(**CONN_PARAMS)
    avg_row_bytes = measure_avg_row_bytes(conn, "customer")
    print(f"measured avg CUSTOMER row size on disk: {avg_row_bytes:.1f} bytes")

    results = []
    district_id = NEXT_DISTRICT_ID
    for batch_size in BATCH_SIZES:
        for trial in range(TRIALS_PER_SIZE):
            r = run_trial(conn, batch_size, district_id)
            r["trial"] = trial
            r["avg_row_bytes"] = avg_row_bytes
            r["actual_data_bytes"] = avg_row_bytes * batch_size
            results.append(r)
            print(f"batch={batch_size:5d} trial={trial}  "
                  f"boxes={r['n_boxes']} exc={r['n_exceptions']}  "
                  f"storage ratio={r['box_bytes']/r['naive_bytes']:.3f}x  "
                  f"log_time ratio={r['box_log_time']/max(r['naive_log_time'],1e-9):.2f}x")
            district_id += 1  # fresh district every trial, no cross-trial contamination
    conn.close()

    with open("insert_sweep_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {len(results)} rows to insert_sweep_results.csv")