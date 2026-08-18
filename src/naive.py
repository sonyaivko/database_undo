"""
Naive baseline for undoing INSERTs: log every inserted row's PK, undo by
DELETE ... WHERE pk IN (...).

"""
import json
import time


def naive_log_insertion(batch_rows, pk_cols):
    return [tuple(r[c] for c in pk_cols) for r in batch_rows]


def naive_storage_bytes(pk_list):
    return len(json.dumps(pk_list, default=str))


def naive_undo_insertion(conn, table, pk_list, pk_cols):
    if not pk_list:
        return 0
    from psycopg2 import sql as pgsql
    cur = conn.cursor()
    cols_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk_cols)
    row_tuples = pgsql.SQL(", ").join(
        pgsql.SQL("({})").format(pgsql.SQL(", ").join(pgsql.Literal(v) for v in t))
        for t in pk_list
    )
    q = pgsql.SQL("DELETE FROM {} WHERE ({}) IN ({})").format(
        pgsql.Identifier(table.lower()), cols_sql, row_tuples)
    cur.execute(q)
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n