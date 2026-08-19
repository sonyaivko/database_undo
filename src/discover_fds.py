"""
- Runs Desbordante's HyFD on a CSV 
- raw HyFD output is dominated by spurious FDs from near-unique columns

usage: python3 discover_fds.py <csv_path> <pk_col1> [pk_col2 ...]
writes <csv_path>_fds.json with the FD list lhs -> rhs 
"""
import sys
import json
import desbordante
from fd_filter import load_csv_rows, filter_usable_fds


def discover(csv_path, pk_cols, min_avg_group_size=2.0):
    algo = desbordante.fd.algorithms.HyFD()
    algo.load_data(table=(csv_path, ",", True))
    algo.execute()
    raw_fds = algo.get_fds()

    parsed = []
    for fd in raw_fds:
        lhs_str, rhs = str(fd).split("->")
        lhs = lhs_str.strip("[] ").split()
        parsed.append((lhs, rhs.strip()))

    rows = load_csv_rows(csv_path)
    usable = filter_usable_fds(parsed, rows, min_avg_group_size=min_avg_group_size,
                                exclude_cols=pk_cols)
    return len(raw_fds), usable


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 discover_fds.py <csv_path> <pk_col1> [pk_col2 ...]")
        sys.exit(1)

    csv_path = sys.argv[1]
    pk_cols = sys.argv[2:]

    n_raw, usable = discover(csv_path, pk_cols)
    print(f"{n_raw} raw FDs -> {len(usable)} usable after filtering (PK excluded: {pk_cols})\n")
    for lhs, rhs, ags in sorted(usable, key=lambda x: -x[2]):
        print(f"  {lhs} -> {rhs}   (avg group size: {ags:.1f})")

    out_path = csv_path.rsplit(".", 1)[0] + "_fds.json"
    with open(out_path, "w") as f:
        json.dump([{"lhs": lhs, "rhs": rhs, "avg_group_size": ags} for lhs, rhs, ags in usable], f, indent=2)
    print(f"\nWrote {out_path}")
