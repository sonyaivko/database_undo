"""
FD-patch vs naive full-row-image baseline, across batch sizes.

Usage: python3 sweep_delete.py <fds_json> <table> <pk_col1> [pk_col2 ...]
Example (NCVoter): python3 sweep_delete.py ncvoter_trimmed_fds.json ncvoter ncid
Example (TPC-C):    python3 sweep_delete.py customer_snapshot_fds.json customer c_w_id c_d_id c_id

"""
import sys
import csv
import json
import time
import psycopg2
from psycopg2.extras import RealDictCursor

from fd_graph import build_dependency_graph
from fd_patch_lib import log_deletion, undo_deletion
from naive_delete_lib import naive_log_deletion, naive_storage_bytes, naive_undo_deletion

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")

BATCH_SIZES = [5, 10, 25, 50, 100, 250, 500, 1000]
TRIALS_PER_SIZE = 3


def fetch_batch(conn, table, pk_cols, offset, limit):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    order_by = ", ".join(pk_cols)
    cur.execute(f"SELECT * FROM {table} ORDER BY {order_by} OFFSET %s LIMIT %s", (offset, limit))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def run_trial(conn, table, pk_cols, rules, topo_order, offset, batch_size):
    rows = fetch_batch(conn, table, pk_cols, offset, batch_size)
    if len(rows) < batch_size:
        raise RuntimeError(f"Ran out of rows at offset {offset} (got {len(rows)}, wanted {batch_size}) "
                            f"-- table is smaller than the sweep needs; lower BATCH_SIZES/TRIALS_PER_SIZE.")

    pk_dicts = [{c: r[c] for c in pk_cols} for r in rows]

    #  FD-patch path 
    t0 = time.perf_counter()
    fd_logged = []
    for row in rows:
        predictors, fd_patch = log_deletion(conn, table, row, pk_cols, rules, batch_pks=pk_dicts)
        fd_logged.append((predictors, fd_patch))
    fd_log_time = time.perf_counter() - t0
    fd_bytes = sum(naive_storage_bytes([p]) + naive_storage_bytes([f]) for p, f in fd_logged)

    cur = conn.cursor()
    for pk in pk_dicts:
        where = " AND ".join(f"{c}=%s" for c in pk_cols)
        cur.execute(f"DELETE FROM {table} WHERE {where}", list(pk.values()))
    conn.commit()
    cur.close()

    t0 = time.perf_counter()
    for pk, (predictors, fd_patch) in zip(pk_dicts, fd_logged):
        undo_deletion(conn, table, pk, predictors, fd_patch, rules, topo_order)
    fd_undo_time = time.perf_counter() - t0

    # naive path
    t0 = time.perf_counter()
    naive_logged = [naive_log_deletion(row) for row in rows]
    naive_log_time = time.perf_counter() - t0
    naive_bytes = naive_storage_bytes(naive_logged)

    cur = conn.cursor()
    for pk in pk_dicts:
        where = " AND ".join(f"{c}=%s" for c in pk_cols)
        cur.execute(f"DELETE FROM {table} WHERE {where}", list(pk.values()))
    conn.commit()
    cur.close()

    t0 = time.perf_counter()
    for row in naive_logged:
        naive_undo_deletion(conn, table, row)
    naive_undo_time = time.perf_counter() - t0

    return dict(
        batch_size=batch_size,
        fd_log_time=fd_log_time, fd_undo_time=fd_undo_time, fd_bytes=fd_bytes,
        naive_log_time=naive_log_time, naive_undo_time=naive_undo_time, naive_bytes=naive_bytes,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    fds_json, table = sys.argv[1], sys.argv[2]
    pk_cols = sys.argv[3:]

    conn = psycopg2.connect(**CONN_PARAMS)

    with open(fds_json) as f:
        fd_data = json.load(f)
    usable = [(d["lhs"], d["rhs"], d["avg_group_size"]) for d in fd_data]
    graph, rules, topo_order = build_dependency_graph(usable)
    print(f"{len(rules)} derivable columns, using {sum(1 for _ in rules)} rules from {fds_json}")

    results = []
    offset = 0
    for batch_size in BATCH_SIZES:
        for trial in range(TRIALS_PER_SIZE):
            r = run_trial(conn, table, pk_cols, rules, topo_order, offset, batch_size)
            r["trial"] = trial
            results.append(r)
            print(f"batch={batch_size:5d} trial={trial}  "
                  f"storage ratio={r['fd_bytes']/r['naive_bytes']:.3f}x  "
                  f"log_time ratio={r['fd_log_time']/max(r['naive_log_time'],1e-9):.2f}x  "
                  f"undo_time ratio={r['fd_undo_time']/max(r['naive_undo_time'],1e-9):.2f}x")
            offset += batch_size
    conn.close()

    out_csv = "delete_sweep_results.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {len(results)} rows to {out_csv}")