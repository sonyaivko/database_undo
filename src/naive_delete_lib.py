"""
store the entire row, undo by direct re-INSERT
"""
import json
from psycopg2 import sql as pgsql


def naive_log_deletion(row):
    return dict(row)


def naive_storage_bytes(logged_rows):
    return len(json.dumps(logged_rows, default=str))


def naive_undo_deletion(conn, table, row):
    cur = conn.cursor()
    cols = list(row.keys())
    col_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols)
    placeholders = pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols)
    cur.execute(
        pgsql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            pgsql.Identifier(table.lower()), col_sql, placeholders),
        [row[c] for c in cols])
    conn.commit()
    cur.close()