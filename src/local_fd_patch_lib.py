"""
logDeletion/UndoDeletion built on top of local_fd_discovery

"""
from psycopg2 import sql as pgsql


def topological_order(rules):
    """ DFS post-order, correct as long as rules is acyclic"""
    order = []
    visited = set()

    def visit(col):
        if col in visited:
            return
        visited.add(col)
        if col in rules:
            for src in rules[col]["source"]:
                visit(src)
        order.append(col)

    for col in list(rules.keys()):
        visit(col)
    return order


def log_batch_deletion(batch_rows, pk_cols, rules):
    """Returns (deleted_log, fd_patch), both keyed by PK tuple.
    deleted_log[pk] = {predictor_col: value, ...} columns
        with no rule.
    fd_patch[pk] = {ruled_col: actual_value, ...} exceptions only."""
    if not batch_rows:
        return {}, {}

    all_cols = [c for c in batch_rows[0].keys() if c not in pk_cols]
    predictor_cols = [c for c in all_cols if c not in rules]

    deleted_log, fd_patch = {}, {}
    for row in batch_rows:
        pk = tuple(row[c] for c in pk_cols)
        deleted_log[pk] = {c: row[c] for c in predictor_cols}

        patches = {}
        for target, rule in rules.items():
            key = tuple(row[c] for c in rule["source"])
            if rule["mapping"].get(key) != row[target]:
                patches[target] = row[target]
        fd_patch[pk] = patches

    return deleted_log, fd_patch


def undo_row(pk_vals, predictors, patches, rules, topo_order):
    """Reconstructs one row's full column dict """
    reconstructed = dict(pk_vals)
    reconstructed.update(predictors)

    for col in topo_order:
        if col in reconstructed:
            continue
        if col not in rules:
            continue  
        if col in patches:
            reconstructed[col] = patches[col]
            continue
        rule = rules[col]
        key = tuple(reconstructed[c] for c in rule["source"])
        value = rule["mapping"].get(key)
        if value is None:
            raise ValueError(
                f"Cannot reconstruct column '{col}' for {pk_vals}: no mapping entry for "
                f"key {key}. "
            )
        reconstructed[col] = value

    return reconstructed


def undo_batch_deletion(conn, table, pk_cols, deleted_log, fd_patch, rules, topo_order):
    """Reconstructs and reinserts every row captured in deleted_log/fd_patch.
    Returns the count inserted """
    cur = conn.cursor()
    inserted = 0
    for pk, predictors in deleted_log.items():
        pk_vals = dict(zip(pk_cols, pk))
        patches = fd_patch.get(pk, {})
        reconstructed = undo_row(pk_vals, predictors, patches, rules, topo_order)

        cols = list(reconstructed.keys())
        col_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols)
        placeholders = pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols)
        cur.execute(
            pgsql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                pgsql.Identifier(table.lower()), col_sql, placeholders),
            [reconstructed[c] for c in cols])
        inserted += 1

    conn.commit()
    cur.close()
    return inserted