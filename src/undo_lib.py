"""
Day 2: logInsertion / findPartitions / UndoInsertion, implemented against
real Postgres so contamination() and countInBox() are real SQL, not mocked.

Design note / amendment flagged to the user:
    createBoundingBox bounds ALL columns, not just the "varying" ones.
    - varying columns (>1 distinct value in the batch) -> range (numeric) or
      set (categorical) condition, and count toward numDims.
    - constant columns (1 distinct value) -> equality condition, but do NOT
      count toward numDims.
    Rationale: omitting constant columns from the box's WHERE clause makes
    the box's scope far too wide (e.g. a C_ID range with no C_W_ID/C_D_ID
    filter matches every other district), which corrupts both the
    contamination measurement and, at undo time, risks deleting unrelated
    rows inserted later by other transactions.

Open design question (Day 2, not yet resolved): maxGapSplit here only
considers numeric/orderable columns. Categorical (string) columns still get
a set-membership condition in the box, but they are not currently candidates
for the *split* dimension -- that needs a defined "gap" notion for
unordered categoricals (e.g. frequency-based bucketing) which the original
pseudocode doesn't specify. Flagging rather than inventing one silently.
"""
import datetime
import psycopg2
from psycopg2 import sql as pgsql

MIN_PROGRESS = 2.0  # tunable; see Day 3 sweep

# A categorical column only earns a spot in the box if its distinct-value
# count is at or below this cap -- above it, a "set" condition costs as much
# as just listing the rows, so it buys no compression. Tunable; worth
# sweeping in Day 3 (higher cap = more selective boxes but bigger to store).
CATEGORICAL_CARDINALITY_CAP = 10

NUMERIC_TYPES = (int, float, datetime.datetime, datetime.date)


def is_numeric(v):
    return isinstance(v, NUMERIC_TYPES) and not isinstance(v, bool)


def pk_tuple(row, pk_cols):
    return tuple(row[c] for c in pk_cols)


def compute_dims(rows, cols):
    """Classifies each column for this batch into:
      - constant: single distinct value -> free equality condition
      - cheap_varying: numeric/datetime range, OR categorical at/under the
        cardinality cap -> counts toward numDims, included in the box
      - expensive_varying: high-cardinality categorical -> excluded from
        both numDims and the box entirely; a set condition here costs as
        much as listing the rows, so it can't help compression.
    Returns (cheap_varying, constant, expensive_varying).
    """
    cheap, constant, expensive = [], [], []
    for c in cols:
        distinct = set(r[c] for r in rows)
        if len(distinct) == 1:
            constant.append(c)
        elif is_numeric(next(iter(distinct))):
            cheap.append(c)
        elif len(distinct) <= CATEGORICAL_CARDINALITY_CAP:
            cheap.append(c)
        else:
            expensive.append(c)
    return cheap, constant, expensive


def create_bounding_box(rows, cheap_varying, constant_cols):
    """Note: expensive_varying columns are deliberately NOT passed in here --
    they never appear in the box (see compute_dims docstring)."""
    box = {"range": {}, "set": {}, "eq": {}}
    for c in constant_cols:
        box["eq"][c] = rows[0][c]
    for c in cheap_varying:
        vals = [r[c] for r in rows]
        if is_numeric(vals[0]):
            box["range"][c] = (min(vals), max(vals))
        else:
            box["set"][c] = set(vals)
    return box


def box_where_clause(box):
    """Builds a parameterized WHERE clause + params list for the box."""
    clauses, params = [], []
    for c, v in box["eq"].items():
        clauses.append(pgsql.SQL("{} = %s").format(pgsql.Identifier(c)))
        params.append(v)
    for c, (lo, hi) in box["range"].items():
        clauses.append(pgsql.SQL("{} BETWEEN %s AND %s").format(pgsql.Identifier(c)))
        params.extend([lo, hi])
    for c, vals in box["set"].items():
        clauses.append(pgsql.SQL("{} = ANY(%s)").format(pgsql.Identifier(c)))
        params.append(list(vals))
    return pgsql.SQL(" AND ").join(clauses), params


def count_in_box(conn, table, box):
    where, params = box_where_clause(box)
    q = pgsql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(pgsql.Identifier(table.lower()), where)
    cur = conn.cursor()
    cur.execute(q, params)
    n = cur.fetchone()[0]
    cur.close()
    return n


def contamination(conn, table, box, n_new):
    """Ratio of (rows matched by box beyond the new batch) to (new batch rows in box).
    0 = perfectly pure (no old rows captured). Higher = worse."""
    total = count_in_box(conn, table, box)
    old = total - n_new
    if old < 0:
        # Shouldn't happen if box truly contains all n_new rows; guard anyway.
        old = 0
    return old / n_new if n_new else float("inf")


def max_gap_split(rows, varying_cols):
    """Only considers numeric/orderable columns (see module docstring)."""
    best = None  # (normalized_gap, dim, cut_val)
    for c in varying_cols:
        vals = sorted(set(r[c] for r in rows))
        if len(vals) < 2 or not is_numeric(vals[0]):
            continue
        span = vals[-1] - vals[0]
        if isinstance(span, datetime.timedelta):
            span = span.total_seconds()
            if span == 0:
                continue
        elif span == 0:
            continue
        for i in range(len(vals) - 1):
            gap = vals[i + 1] - vals[i]
            gap_sec = gap.total_seconds() if isinstance(gap, datetime.timedelta) else gap
            norm = gap_sec / span
            if best is None or norm > best[0]:
                mid = vals[i] + (vals[i + 1] - vals[i]) / 2 if not isinstance(vals[i], datetime.datetime) \
                    else vals[i] + (vals[i + 1] - vals[i]) / 2
                best = (norm, c, mid)
    if best is None:
        return None, None
    return best[1], best[2]


def find_partitions(conn, table, rows, pk_cols, boxes, exception_ids):
    if not rows:
        return
    cols = list(rows[0].keys())
    cheap, constant, _expensive = compute_dims(rows, cols)
    numDims = len(cheap)
    if len(rows) < 2 * numDims:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in rows)
        return
    box = create_bounding_box(rows, cheap, constant)
    if count_in_box(conn, table, box) == len(rows):
        boxes.append(box)
        return
    dim, val = max_gap_split(rows, cheap)
    if dim is None:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in rows)
        return
    left = [r for r in rows if r[dim] <= val]
    right = [r for r in rows if r[dim] > val]
    find_partitions(conn, table, left, pk_cols, boxes, exception_ids)
    find_partitions(conn, table, right, pk_cols, boxes, exception_ids)


def log_insertion(conn, table, batch_rows, pk_cols):
    boxes, exception_ids = [], []
    cols = list(batch_rows[0].keys())
    cheap, constant, _expensive = compute_dims(batch_rows, cols)
    numDims = len(cheap)
    if len(batch_rows) < 2 * numDims:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in batch_rows)
        return boxes, exception_ids
    box = create_bounding_box(batch_rows, cheap, constant)
    if count_in_box(conn, table, box) == len(batch_rows):
        boxes.append(box)
        return boxes, exception_ids
    dim, val = max_gap_split(batch_rows, cheap)
    if dim is None:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in batch_rows)
        return boxes, exception_ids
    left = [r for r in batch_rows if r[dim] <= val]
    right = [r for r in batch_rows if r[dim] > val]
    box_left = create_bounding_box(left, *compute_dims(left, cols)[:2])
    box_right = create_bounding_box(right, *compute_dims(right, cols)[:2])
    cL = contamination(conn, table, box_left, len(left))
    cR = contamination(conn, table, box_right, len(right))
    c_parent = contamination(conn, table, box, len(batch_rows))
    proceed = (min(cL, cR) == 0) or (c_parent / min(cL, cR) >= MIN_PROGRESS if min(cL, cR) else True)
    if not proceed:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in batch_rows)
        return boxes, exception_ids
    find_partitions(conn, table, left, pk_cols, boxes, exception_ids)
    find_partitions(conn, table, right, pk_cols, boxes, exception_ids)
    return boxes, exception_ids


def undo_insertion(conn, table, boxes, exception_ids, pk_cols):
    cur = conn.cursor()
    deleted = 0
    for box in boxes:
        where, params = box_where_clause(box)
        q = pgsql.SQL("DELETE FROM {} WHERE {}").format(pgsql.Identifier(table.lower()), where)
        cur.execute(q, params)
        deleted += cur.rowcount
    if exception_ids:
        cols_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk_cols)
        row_tuples = pgsql.SQL(", ").join(
            pgsql.SQL("({})").format(pgsql.SQL(", ").join(pgsql.Literal(v) for v in t))
            for t in exception_ids
        )
        q = pgsql.SQL("DELETE FROM {} WHERE ({}) IN ({})").format(
            pgsql.Identifier(table.lower()), cols_sql, row_tuples)
        cur.execute(q)
        deleted += cur.rowcount
    conn.commit()
    cur.close()
    return deleted
