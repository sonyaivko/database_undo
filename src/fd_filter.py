"""
- filters raw FD-discovery output
- drops FDs with low average group size and near-constant RHS columns 
to avoid overfitting 

"""
import csv

def load_csv_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def avg_group_size(rows, lhs_cols):
    if not lhs_cols:
        return len(rows)  # empty LHS = one group 
    groups = set()
    for r in rows:
        groups.add(tuple(r[c] for c in lhs_cols))
    return len(rows) / len(groups)

def rhs_majority_fraction(rows, rhs_col):
    from collections import Counter
    counts = Counter(r[rhs_col] for r in rows)
    return counts.most_common(1)[0][1] / len(rows)

def filter_usable_fds(fds, rows, min_avg_group_size=2.0, exclude_cols=(), max_rhs_majority_fraction=0.98):
    """fds: list of (lhs_cols: list[str], rhs_col: str) tuples.
    exclude_cols: columns to drop from LHS consideration outright."""
    usable = []
    for lhs, rhs in fds:
        if any(c in exclude_cols for c in lhs): # do not consider PK 
            continue
        # check that the RHS is not overfitting/ the exception.
        # if a column is 99% same + 1 off, the 1 off does not create a FD 
        if lhs and rhs_majority_fraction(rows, rhs) >= max_rhs_majority_fraction: 
            continue

        # check that the predictor is common enough 
        ags = avg_group_size(rows, lhs)
        if ags >= min_avg_group_size:
            usable.append((lhs, rhs, ags))
    return usable
