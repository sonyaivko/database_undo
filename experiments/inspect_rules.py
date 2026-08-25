"""
Usage: python3 inspect_rules.py <table> <batch_size> <pk_col1> [pk_col2 ...]
Example (NCVoter): python3 inspect_rules.py ncvoter 1000 ncid
"""
import sys
import csv
import psycopg2
from psycopg2.extras import RealDictCursor
from local_fd_discovery import discover_rules

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    table, batch_size = sys.argv[1], int(sys.argv[2])
    pk_cols = sys.argv[3:]

    conn = psycopg2.connect(**CONN_PARAMS)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    order_by = ", ".join(pk_cols)
    cur.execute(f"SELECT * FROM {table} ORDER BY {order_by} LIMIT {batch_size}")
    batch = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    rules = discover_rules(batch, pk_cols)
    ranked = sorted(rules.items(), key=lambda x: -x[1]["bytes_saved"])

    out_csv = "rule_bytes_saved.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "target_column", "source_columns", "bytes_saved",
                          "bytes_still_needed", "coverage", "likely_real"])
        for rank, (target, r) in enumerate(ranked, 1):
            writer.writerow([rank, target, "+".join(r["source"]) or "(constant)",
                              r["bytes_saved"], r["bytes_still_needed"],
                              round(r["coverage"], 3), r["likely_real"]])
            print(f"{rank:2d}. {target:20s} <- {'+'.join(r['source']) or '(constant)':25s} "
                  f"saved={r['bytes_saved']:6d} bytes  coverage={r['coverage']:.3f}  likely_real={r['likely_real']}")

    print(f"\nWrote {out_csv}")