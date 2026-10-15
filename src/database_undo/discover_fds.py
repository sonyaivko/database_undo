"""Global functional-dependency discovery over a whole table.

FDs are written to JSON.

Command line:

python3 -m database_undo.discover_fds <csv_path> <pk_col> [pk_col ...]

Writes `<csv_path minus extension>_fds.json`.

"""

import os
import sys
import json

from .fd_filter import load_csv_rows, filter_usable_fds


def discover(csv_path, pk_cols, min_avg_group_size=2.0):
    """Mines FDs from a CSV and drops the ones that are not worth storing.

    - `csv_path` (str): path to a comma-separated file whose first row is a
      header.
    - `pk_cols` (list of str): primary-key columns. Excluded from every
      left-hand side, since a key determines everything and predicts
      nothing useful.
    - `min_avg_group_size` (float, optional): the smallest average number of
      rows per left-hand-side group an FD may have and still be kept.
      Defaults to 2.0.
    - Returns: `(n_raw, usable)`, where `n_raw` is how many FDs HyFD
      reported and `usable` is a list of `(lhs_cols, rhs_col,
      avg_group_size)` triples.
    - Raises: `ImportError` if Desbordante is not installed.
    """
    try:
        import desbordante
    except ImportError as exc: 
        raise ImportError(
            "Global FD discovery needs Desbordante. Install it with "
            "`pip install 'database-undo[discovery]'` or `pip install desbordante`. "
            "The per-batch discovery in database_undo.local_fd_discovery "
            "needs no extra packages."
        ) from exc

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


def main(argv=None):
    """Command-line entry point. Returns a process exit status."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) < 2:
        prog = os.path.basename(sys.argv[0]) or "dbundo-discover-fds"
        print(f"Usage: {prog} <csv_path> <pk_col> [pk_col ...]")
        return 1

    csv_path = argv[0]
    pk_cols = argv[1:]

    n_raw, usable = discover(csv_path, pk_cols)
    print(f"{n_raw} raw FDs -> {len(usable)} usable after filtering "
          f"(PK excluded: {pk_cols})\n")
    for lhs, rhs, ags in sorted(usable, key=lambda x: -x[2]):
        print(f"  {lhs} -> {rhs}   (avg group size: {ags:.1f})")

    out_path = csv_path.rsplit(".", 1)[0] + "_fds.json"
    with open(out_path, "w") as f:
        json.dump([{"lhs": lhs, "rhs": rhs, "avg_group_size": ags}
                   for lhs, rhs, ags in usable], f, indent=2)
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())