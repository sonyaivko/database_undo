"""
Insertion sweep: box-based logInsertion vs naive PK-list baseline, as a function
of batch size.

Produces graph 1 and 2 for the plot. 
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
W_ID, D_ID = 1, 40

BATCH_SIZES = [10, 25, 50, 100, 250, 500, 1000, 2000]
TRIALS_PER_SIZE = 5

# creating a new district far from old data 
RECLAIMED_SLOT_STRIDE = 3000   
FRESH_BASE_OFFSET = 10_000_000  
FRESH_SLOT_STRIDE = 3000

def setup_district(conn, old_data_max_id):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM DISTRICT WHERE d_id=%s AND d_w_id=%s", (D_ID, W_ID))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO DISTRICT VALUES (%s,%s,'D_split','x','x','x','MA','000011111',0.05,30000.0,3001)",
            (D_ID, W_ID))
        conn.commit()
    cur.execute("DELETE FROM CUSTOMER WHERE c_w_id=%s AND c_d_id=%s", (W_ID, D_ID))
    conn.commit()
    cur.close()
 
    print(f"Populating dense old data (1..{old_data_max_id})...")
    old_rows = [make_customer_row(cid, D_ID, W_ID) for cid in range(1, old_data_max_id + 1)]
    cur = conn.cursor()
    cols = list(old_rows[0].keys())
    execute_values(cur, f"INSERT INTO CUSTOMER ({','.join(cols)}) VALUES %s",
                    [[r[c] for c in cols] for r in old_rows], page_size=1000)
    conn.commit()
    cur.close()
 
 
def timed_insert_rows(conn, rows):
    cur = conn.cursor()
    cols = list(rows[0].keys())
    t0 = time.perf_counter()
    execute_values(cur, f"INSERT INTO CUSTOMER ({','.join(cols)}) VALUES %s",
                    [[r[c] for c in cols] for r in rows], page_size=500)
    conn.commit()
    dt = time.perf_counter() - t0
    cur.close()
    return dt 
 
 
def run_trial(conn, batch_size, slot_index, since_lo, since_hi):
    import random
    import datetime
 
    cluster_a_size = batch_size // 2
    cluster_b_size = batch_size - cluster_a_size
 
    reclaimed_start = 1000 + slot_index * RECLAIMED_SLOT_STRIDE
    reclaimed_ids = list(range(reclaimed_start, reclaimed_start + cluster_a_size))
 
    fresh_start = FRESH_BASE_OFFSET + slot_index * FRESH_SLOT_STRIDE
    fresh_ids = list(range(fresh_start, fresh_start + cluster_b_size))
 
    cur = conn.cursor()
    for cid in reclaimed_ids:
        cur.execute("DELETE FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s", (W_ID, D_ID, cid))
    conn.commit()
    cur.close()
 
    batch = ([make_customer_row(cid, D_ID, W_ID) for cid in reclaimed_ids] +
             [make_customer_row(cid, D_ID, W_ID) for cid in fresh_ids])
    since_span = (since_hi - since_lo).total_seconds()
    for row in batch:
        row["c_since"] = since_lo + datetime.timedelta(seconds=random.uniform(0, since_span))
 
    plain_insert_time_1 = timed_insert_rows(conn, batch)

 
    t0 = time.perf_counter()
    boxes, exceptions = log_insertion(conn, "customer", batch, PK_COLS)
    box_log_time = time.perf_counter() - t0
    box_bytes = len(json.dumps(boxes, default=str)) + len(json.dumps(exceptions))
 
    t0 = time.perf_counter()
    deleted = undo_insertion(conn, "customer", boxes, exceptions, PK_COLS)
    box_undo_time = time.perf_counter() - t0
 
    # naive baseline on the same batch, reinserted fresh
    for cid in reclaimed_ids:
        cur = conn.cursor()
        cur.execute("DELETE FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s", (W_ID, D_ID, cid))
        cur.close()
    conn.commit()
    plain_insert_time_2 = timed_insert_rows(conn, batch)
 
    t0 = time.perf_counter()
    pk_list = naive_log_insertion(batch, PK_COLS)
    naive_log_time = time.perf_counter() - t0
    naive_bytes = naive_storage_bytes(pk_list)
 
    t0 = time.perf_counter()
    naive_undo_insertion(conn, "customer", pk_list, PK_COLS)
    naive_undo_time = time.perf_counter() - t0
 
    correctness_ok = (len(boxes) == 2 and len(exceptions) == 0 and deleted == len(batch))
 
    return dict(
        batch_size=batch_size, n_boxes=len(boxes), n_exceptions=len(exceptions),
        box_log_time=box_log_time, box_undo_time=box_undo_time, box_bytes=box_bytes,
        naive_log_time=naive_log_time, naive_undo_time=naive_undo_time, naive_bytes=naive_bytes,
        plain_insert_time=(plain_insert_time_1 + plain_insert_time_2) / 2,
        correctness_ok=correctness_ok,
    )
 
 
if __name__ == "__main__":
    conn = psycopg2.connect(**CONN_PARAMS)
 
    n_trials_total = len(BATCH_SIZES) * TRIALS_PER_SIZE
    old_data_max_id = n_trials_total * RECLAIMED_SLOT_STRIDE + RECLAIMED_SLOT_STRIDE
    setup_district(conn, old_data_max_id)
 
    cur = conn.cursor()
    cur.execute("SELECT MIN(c_since), MAX(c_since) FROM customer WHERE c_w_id=%s AND c_d_id=%s", (W_ID, D_ID))
    since_lo, since_hi = cur.fetchone()
    cur.close()
 
    results = []
    slot_index = 0
    for batch_size in BATCH_SIZES:
        for trial in range(TRIALS_PER_SIZE):
            r = run_trial(conn, batch_size, slot_index, since_lo, since_hi)
            r["trial"] = trial
            results.append(r)
            status = "OK" if r["correctness_ok"] else "MISMATCH"
            print(f"batch={batch_size:5d} trial={trial}  boxes={r['n_boxes']} (expected 2) exc={r['n_exceptions']}  "
                  f"storage ratio={r['box_bytes']/r['naive_bytes']:.3f}x  "
                  f"log_time ratio={r['box_log_time']/max(r['naive_log_time'],1e-9):.2f}x  [{status}]")
            slot_index += 1
    conn.close()
 
    with open("insert_sweep_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {len(results)} rows to insert_sweep_results.csv")
 
    n_mismatches = sum(1 for r in results if not r["correctness_ok"])
    if n_mismatches:
        print(f"\nWARNING: {n_mismatches} trial(s) did not produce the expected 2-box, 0-exception split")
    else:
        print("\nAll trials correctly forced exactly one split (2 boxes, 0 exceptions).")
 