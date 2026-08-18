"""
logInsertion / findPartitions / UndoInsertion

    createBoundingBox bounds ALL columns, not just the "varying" ones.
    - varying columns (>1 distinct value in the batch) -> range (numeric) or

Notes:    
    - maxGapSplit here only considers numeric/orderable columns.
    Categorical (string) columns still get a set-membership condition in the box, but aren't
    candidates for the *split* dimension. 
"""
import datetime
import psycopg2
from psycopg2 import sql as pgsql

# progress tracker variable 
MIN_PROGRESS = 2.0  

# max cardinality considered before falling back to exception IDs 
CATEGORICAL_CARDINALITY_CAP = 10

NUMERIC_TYPES = (int, float, datetime.datetime, datetime.date)

def is_numeric(v):
    return isinstance(v, NUMERIC_TYPES) and not isinstance(v, bool)

def pk_tuple(row, pk_cols):
    return tuple(row[c] for c in pk_cols)

def compute_dims(rows, cols):
    """Classifies each column:
      - constant: single distinct value 
      - cheap_varying: numeric/datetime range, or categorical at/under 
        categorical_cardinality_cap -> counts toward numDims
      - expensive_varying: excluded from both numDims and the box  

    returns (cheap_varying, constant, expensive_varying).
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
   # creates bounding box based off the MIN and MAX
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
    # builds a parameterized WHERE clause for the box. 
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
    # returns the total number of rows in the table that match the bounding box 
    where, params = box_where_clause(box)
    q = pgsql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(pgsql.Identifier(table.lower()), where)
    cur = conn.cursor()
    cur.execute(q, params)
    n = cur.fetchone()[0]
    cur.close()
    return n


def contamination(conn, table, box, n_new):
    # returns the ratio of old / new batch rows in box
    # 0 = PURE, no old rows 
    total = count_in_box(conn, table, box)
    old = total - n_new
    if old < 0:
        old = 0
    return old / n_new if n_new else float("inf")


def max_gap_split(rows, varying_cols):
    # Finds the split with the largest numerical gap.
    # categorical splitting is unimplemented. 

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
    numDims = len(cheap) # number of columns that the CURRENT candidate box would need to bound 
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

    # if batch is small enough, storing IDs is cheaper
    if len(batch_rows) < 2 * numDims:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in batch_rows)
        return boxes, exception_ids
    box = create_bounding_box(batch_rows, cheap, constant)

    # perfectly bounded 
    if count_in_box(conn, table, box) == len(batch_rows):
        boxes.append(box)
        return boxes, exception_ids
    
    dim, val = max_gap_split(batch_rows, cheap)
    # no gap exists (low=high everywhere)
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

    # if split results in at least one child box to be MIN_PROGRESS times more pure than original, continue. 
    proceed = True if min(cL, cR) == 0 else (c_parent / min(cL, cR) >= MIN_PROGRESS)   
    if not proceed:
        exception_ids.extend(pk_tuple(r, pk_cols) for r in batch_rows)
        return boxes, exception_ids

    # recursive calls
    find_partitions(conn, table, left, pk_cols, boxes, exception_ids)
    find_partitions(conn, table, right, pk_cols, boxes, exception_ids)
    return boxes, exception_ids


def undo_insertion(conn, table, boxes, exception_ids, pk_cols):
    # delete via each box's WHERE clause, and exceptions. 
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
