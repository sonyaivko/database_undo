# test bounding box: 
# - check that inserting tuples into an empty region, then undoing correctly deletes all
# - check that inserting tuples into a region with 300 others is correctly undone
# and that other regions are left untouched 

import json
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from undo_lib import log_insertion, undo_insertion, count_in_box
from tpcc_rows import make_customer_row


def box_storage_bytes(boxes, exception_ids):
    return len(json.dumps(boxes, default=str)) + len(json.dumps(exception_ids))


def naive_storage_bytes(pk_tuples):
    return len(json.dumps(pk_tuples))

CONN_PARAMS = dict(host="localhost", port=5432, dbname="undo_test",
                    user="undo_user", password="undo_pass")
PK_COLS = ["c_w_id", "c_d_id", "c_id"]


def insert_rows(conn, rows):
    cur = conn.cursor()
    cols = list(rows[0].keys())
    col_sql = ",".join(cols)
    values = [[r[c] for c in cols] for r in rows]
    execute_values(cur, f"INSERT INTO CUSTOMER ({col_sql}) VALUES %s", values, page_size=500)
    conn.commit()
    cur.close()


def fetch_customers(conn, w_id, d_id, c_id_lo, c_id_hi):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM CUSTOMER WHERE c_w_id=%s AND c_d_id=%s AND c_id BETWEEN %s AND %s",
        (w_id, d_id, c_id_lo, c_id_hi))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def count_customers(conn, w_id, d_id):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM CUSTOMER WHERE c_w_id=%s AND c_d_id=%s", (w_id, d_id))
    n = cur.fetchone()[0]
    cur.close()
    return n


if __name__ == "__main__":
    conn = psycopg2.connect(**CONN_PARAMS)

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM DISTRICT WHERE d_id=11 AND d_w_id=1")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO DISTRICT VALUES (11, 1, 'D1_11', 'x','x','x','MA','000011111', 0.05, 30000.0, 3001)")
        conn.commit()
    cur.close()


    print("=" * 60)
    print("TEST 1: insert with no pre-existing rows -> should be one pure box")
    print("=" * 60)
    new_rows = [make_customer_row(c_id, d_id=11, w_id=1) for c_id in range(1, 41)]
    insert_rows(conn, new_rows)
    before = count_customers(conn, 1, 11)
    boxes, exceptions = log_insertion(conn, "customer", new_rows, PK_COLS)
    print(f"batch size={len(new_rows)}  boxes={len(boxes)}  exceptions={len(exceptions)}")
    naive_ids = [(r["c_w_id"], r["c_d_id"], r["c_id"]) for r in new_rows]
    box_bytes = box_storage_bytes(boxes, exceptions)
    naive_bytes = naive_storage_bytes(naive_ids)
    print(f"  box storage: {box_bytes} bytes  |  naive ID-list storage: {naive_bytes} bytes  "
          f"|  ratio: {box_bytes/naive_bytes:.2f}x")
    for b in boxes:
        print("  box keys used:", {k: list(v.keys()) for k, v in b.items() if v})
    deleted = undo_insertion(conn, "customer", boxes, exceptions, PK_COLS)
    after = count_customers(conn, 1, 11)
    print(f"before undo: {before} rows, deleted: {deleted}, after undo: {after} rows")
    assert after == 0, "FAIL: undo did not remove all inserted rows"
    print("PASS: exact rollback, district 11 empty again\n")

    print("=" * 60)
    print("TEST 2: insert into EXISTING district (w=1,d=5 already has c_id 1..300)")
    print("        new rows use c_id 301..340 (disjoint but adjacent range)")
    print("        checks that constant-column equality (c_w_id, c_d_id) scopes")
    print("        the box correctly and doesn't touch other districts")
    print("=" * 60)
    before_d5 = count_customers(conn, 1, 5)
    before_d6 = count_customers(conn, 1, 6)  # untouched control district
    new_rows2 = [make_customer_row(c_id, d_id=5, w_id=1) for c_id in range(301, 341)]
    insert_rows(conn, new_rows2)
    boxes2, exceptions2 = log_insertion(conn, "customer", new_rows2, PK_COLS)
    print(f"batch size={len(new_rows2)}  boxes={len(boxes2)}  exceptions={len(exceptions2)}")
    naive_ids2 = [(r["c_w_id"], r["c_d_id"], r["c_id"]) for r in new_rows2]
    box_bytes2 = box_storage_bytes(boxes2, exceptions2)
    naive_bytes2 = naive_storage_bytes(naive_ids2)
    print(f"  box storage: {box_bytes2} bytes  |  naive ID-list storage: {naive_bytes2} bytes  "
          f"|  ratio: {box_bytes2/naive_bytes2:.2f}x")
    for b in boxes2:
        print("  box keys used:", {k: list(v.keys()) for k, v in b.items() if v})
    deleted2 = undo_insertion(conn, "customer", boxes2, exceptions2, PK_COLS)
    after_d5 = count_customers(conn, 1, 5)
    after_d6 = count_customers(conn, 1, 6)
    print(f"district 5: before={before_d5+40} (loaded+new), after undo={after_d5}, expected={before_d5}")
    print(f"district 6 (control, must be untouched): before={before_d6}, after={after_d6}")
    assert after_d5 == before_d5, "FAIL: district 5 didn't return to original count"
    assert after_d6 == before_d6, "FAIL: undo touched an unrelated district!"
    print("PASS: exact rollback, no collateral damage to district 6\n")

    conn.close()