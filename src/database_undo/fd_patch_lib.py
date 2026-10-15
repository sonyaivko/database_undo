"""
MVD handling omitted; Desbordante doesn't support MVD discovery 

logDeletion(rowID, deletedRow) -> populates deletedLog, fdPatch
UndoDeletion(rowID) -> reconstructs and reinserts the row

"""
from psycopg2 import sql as pgsql


def get_predictor_columns(all_cols, pk_cols, rules):
    return [c for c in all_cols if c not in pk_cols and c not in rules]


def _lookup_value(conn, table, lhs_cols, lhs_vals, rhs_col, exclude_pks=None, pk_cols=None):
    """Returns the single consistent rhs_col value among rows matching
    lhs_cols=lhs_vals, or None if there's no consistent single value."""
    where_parts = []
    params = []
    for c, v in zip(lhs_cols, lhs_vals):
        where_parts.append(pgsql.SQL("{} = %s").format(pgsql.Identifier(c)))
        params.append(v)
    if exclude_pks:
        cols_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk_cols)
        row_tuples = pgsql.SQL(", ").join(
            pgsql.SQL("({})").format(pgsql.SQL(", ").join(pgsql.Literal(pk[c]) for c in pk_cols))
            for pk in exclude_pks
        )
        where_parts.append(pgsql.SQL("({}) NOT IN ({})").format(cols_sql, row_tuples))
    if not where_parts:
        where_parts = [pgsql.SQL("TRUE")]  # constant column (empty LHS) -- no filter needed
    where = pgsql.SQL(" AND ").join(where_parts)
    q = pgsql.SQL("SELECT DISTINCT {} FROM {} WHERE {}").format(
        pgsql.Identifier(rhs_col), pgsql.Identifier(table.lower()), where)
    cur = conn.cursor()
    cur.execute(q, params)
    rows = cur.fetchall()
    cur.close()
    if len(rows) == 1:
        return rows[0][0]
    return None  # 0 matches 


def log_deletion(conn, table, row, pk_cols, rules, batch_pks = None):
    """row: dict of the full deleted row's values, captured before the
    physical DELETE (or from a trigger's OLD record)."""
    all_cols = list(row.keys())
    predictor_cols = get_predictor_columns(all_cols, pk_cols, rules)
    predictors = {c: row[c] for c in predictor_cols}

    pk_vals = {c: row[c] for c in pk_cols}
    exclude_pks = batch_pks if batch_pks is not None else [pk_vals]
    fd_patch = {}
    for col, (lhs, _ags) in rules.items():
        lhs_vals = [row[l] for l in lhs]
        expected = _lookup_value(conn, table, lhs, lhs_vals, col, exclude_pks=exclude_pks, pk_cols = pk_cols)
        if expected is None or expected != row[col]:
            fd_patch[col] = row[col]

    return predictors, fd_patch


def undo_deletion(conn, table, pk_vals, predictors, fd_patch, rules, topo_order):
    """pk_vals: dict of this row's PK columns/values.
    predictors, fd_patch: what log_deletion stored for this row.
    Returns the fully reconstructed row dict, and inserts it if it doesn't
    already exist."""
    reconstructed = dict(pk_vals)
    reconstructed.update(predictors)

    for col in topo_order: # walk through topological sort 
        if col in reconstructed:
            continue
        if col not in rules:
            continue  
        if col in fd_patch:
            reconstructed[col] = fd_patch[col]
            continue
        lhs, _ags = rules[col]
        value = _lookup_value(conn, table, lhs, [reconstructed[l] for l in lhs], col)
        if value is None:
            raise ValueError(
                f"Cannot reconstruct column '{col}' for {pk_vals}: no surviving rows "
                f"share its predictor values, and no fdPatch override exists. "
                f"This indicates deletedLog/fdPatch are inconsistent with the current "
                f"table state (e.g. more rows were deleted afterward)."
            )
        reconstructed[col] = value

    cur = conn.cursor()
    where_parts = [pgsql.SQL("{} = %s").format(pgsql.Identifier(c)) for c in pk_vals]
    
    # check if tuple exists 
    cur.execute(
        pgsql.SQL("SELECT 1 FROM {} WHERE {}").format(
            pgsql.Identifier(table.lower()), pgsql.SQL(" AND ").join(where_parts)),
        list(pk_vals.values()))
    exists = cur.fetchone() is not None
    
    # re-insert if it doesn't exist 
    if not exists:
        cols = list(reconstructed.keys())
        col_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols)
        placeholders = pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols)
        cur.execute(
            pgsql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                pgsql.Identifier(table.lower()), col_sql, placeholders),
            [reconstructed[c] for c in cols])
        conn.commit()
    cur.close()
    return reconstructed, exists