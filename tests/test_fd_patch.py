import json
import psycopg2
from psycopg2.extras import RealDictCursor
from fd_graph import build_dependency_graph
from fd_patch_lib import log_deletion, undo_deletion

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")

if __name__ == "__main__":
    args = sys.argv[1:]
    where_clause, limit = "1=1", 5
    if "--where" in args:
        i = args.index("--where")
        where_clause = args[i + 1]
        args = args[:i] + args[i + 2:]
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2:]
 
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    fds_json, table = args[0], args[1]
    PK_COLS = args[2:]
    if not PK_COLS:
        print("Need at least one PK column")
        sys.exit(1)
 
    conn = psycopg2.connect(**CONN_PARAMS)
 
    with open(fds_json) as f:
        fd_data = json.load(f)
    usable = [(d["lhs"], d["rhs"], d["avg_group_size"]) for d in fd_data]
    graph, rules, topo_order = build_dependency_graph(usable)
    print("Derivation rules:", {k: v[0] for k, v in rules.items()})
    print("Topo order:", topo_order)
    print()
 
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(f"SELECT * FROM {table} WHERE {where_clause} LIMIT {limit}")
    victims = [dict(r) for r in cur.fetchall()]
    cur.close()
 
    if not victims:
        print(f"No rows matched WHERE {where_clause} -- nothing to test. Adjust --where.")
        sys.exit(1)
 
    print(f"Testing on {len(victims)} real rows from {table}")
    print("=" * 60)
 
    logged = []
    all_batch_pks = [{c: row[c] for c in PK_COLS} for row in victims]
    for row in victims:
        pk_vals = {c: row[c] for c in PK_COLS}
        predictors, fd_patch = log_deletion(conn, table, row, PK_COLS, rules, batch_pks=all_batch_pks)
        logged.append((pk_vals, predictors, fd_patch, row))
        print(f"  row {pk_vals}: {len(predictors)} predictors stored, "
              f"{len(fd_patch)} fdPatch overrides ({list(fd_patch.keys())})")
 
    cur = conn.cursor()
    for pk_vals, _, _, _ in logged:
        where_pk = " AND ".join(f"{c}=%s" for c in PK_COLS)
        cur.execute(f"DELETE FROM {table} WHERE {where_pk}", list(pk_vals.values()))
    conn.commit()
    cur.close()
    print(f"\nDeleted all {len(logged)} rows. Now reconstructing via UndoDeletion...\n")
 
    all_correct = True
    for pk_vals, predictors, fd_patch, original_row in logged:
        reconstructed, existed_already = undo_deletion(
            conn, table, pk_vals, predictors, fd_patch, rules, topo_order)
        mismatches = {c: (original_row[c], reconstructed[c]) for c in original_row
                      if str(original_row[c]) != str(reconstructed[c])}
        status = "EXACT MATCH" if not mismatches else f"MISMATCH: {mismatches}"
        print(f"  row {pk_vals}: {status}")
        if mismatches:
            all_correct = False
 
    print()
    print("PASS: all reconstructed rows exactly match originals" if all_correct
          else "FAIL: some reconstructed rows differ from originals")
    conn.close()