"""
Measures local_fd_discovery + local_fd_patch_lib (discovery, logging, and
reconstruction) against the naive full-row baseline, across batch sizes. 

Usage: python3 sweep_local_fd.py <table> <pk_col1> [pk_col2 ...]
Example (NCVoter): python3 sweep_local_fd.py ncvoter ncid
Example (TPC-C):    python3 sweep_local_fd.py customer c_w_id c_d_id c_id
"""
import sys
import csv
import json
import time
import psycopg2
from psycopg2.extras import RealDictCursor

from local_fd_discovery import discover_rules
from local_fd_patch_lib import topological_order, log_batch_deletion, undo_batch_deletion
from naive_delete_lib import naive_log_deletion, naive_storage_bytes, naive_undo_deletion_batch

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


def naive_bytes_for_batch(rows, pk_cols):
    return sum(len(json.dumps({c: row[c] for c in row if c not in pk_cols}, default=str))
               for row in rows)


def fd_bytes_for_batch(rows, pk_cols, rules):
    all_cols = [c for c in rows[0].keys() if c not in pk_cols]
    ruled_cols = set(rules.keys())
    predictor_cols = [c for c in all_cols if c not in ruled_cols]

    patch_bytes = sum(r["bytes_still_needed"] for r in rules.values())
    mapping_bytes = sum(len(json.dumps(list(r["mapping"].items()), default=str)) for r in rules.values())
    predictor_bytes = sum(len(json.dumps(row[c], default=str)) for row in rows for c in predictor_cols)
    return patch_bytes + mapping_bytes + predictor_bytes


def run_trial(conn, table, pk_cols, offset, batch_size):
    rows = fetch_batch(conn, table, pk_cols, offset, batch_size)
    if len(rows) < batch_size:
        raise RuntimeError(f"Ran out of rows at offset {offset} (got {len(rows)}, wanted {batch_size}) "
                            f"-- table is smaller than the sweep needs; lower BATCH_SIZES/TRIALS_PER_SIZE.")

    pk_tuples = [tuple(row[c] for c in pk_cols) for row in rows]

    # --- local FD-patch path ---
    t0 = time.perf_counter()
    rules = discover_rules(rows, pk_cols)
    discovery_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    deleted_log, fd_patch = log_batch_deletion(rows, pk_cols, rules)
    log_time = time.perf_counter() - t0

    fd_bytes = fd_bytes_for_batch(rows, pk_cols, rules)

    cur = conn.cursor()
    for pk in pk_tuples:
        where = " AND ".join(f"{c}=%s" for c in pk_cols)
        cur.execute(f"DELETE FROM {table} WHERE {where}", pk)
    conn.commit()
    cur.close()

    topo = topological_order(rules)
    t0 = time.perf_counter()
    undo_batch_deletion(conn, table, pk_cols, deleted_log, fd_patch, rules, topo)
    undo_time = time.perf_counter() - t0

    # naive path 
    t0 = time.perf_counter()
    naive_logged = [naive_log_deletion(row) for row in rows]
    naive_log_time = time.perf_counter() - t0
    naive_bytes = naive_storage_bytes(naive_logged)

    cur = conn.cursor()
    for pk in pk_tuples:
        where = " AND ".join(f"{c}=%s" for c in pk_cols)
        cur.execute(f"DELETE FROM {table} WHERE {where}", pk)
    conn.commit()
    cur.close()

    t0 = time.perf_counter()
    naive_undo_deletion_batch(conn, table, naive_logged)
    naive_undo_time = time.perf_counter() - t0

    n_ruled = len(rules)
    n_predictors = len([c for c in rows[0].keys() if c not in pk_cols]) - n_ruled
    n_likely_real = sum(1 for r in rules.values() if r["likely_real"])

    return dict(
        batch_size=batch_size,
        discovery_time=discovery_time, log_time=log_time, undo_time=undo_time,
        naive_log_time=naive_log_time, naive_undo_time=naive_undo_time,
        fd_bytes=fd_bytes, naive_bytes=naive_bytes,
        n_ruled_cols=n_ruled, n_predictor_cols=n_predictors, n_likely_real=n_likely_real,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    table = sys.argv[1]
    pk_cols = sys.argv[2:]

    conn = psycopg2.connect(**CONN_PARAMS)
    results = []
    offset = 0
    for batch_size in BATCH_SIZES:
        for trial in range(TRIALS_PER_SIZE):
            r = run_trial(conn, table, pk_cols, offset, batch_size)
            r["trial"] = trial
            results.append(r)
            print(f"batch={batch_size:5d} trial={trial}  "
                  f"storage ratio={r['fd_bytes']/r['naive_bytes']:.3f}x  "
                  f"discovery={r['discovery_time']*1000:.1f}ms log={r['log_time']*1000:.2f}ms "
                  f"undo={r['undo_time']*1000:.2f}ms  "
                  f"ruled={r['n_ruled_cols']} (likely_real={r['n_likely_real']}) predictors={r['n_predictor_cols']}")
            offset += batch_size
    conn.close()

    out_csv = "local_fd_sweep_results.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {len(results)} rows to {out_csv}")