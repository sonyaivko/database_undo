"""
Checks that log_insertion's split_fn extension point is working
Needs no Postgres and no data: the splitter only uses
the connection to run COUNT(*).

Usage: python3 tests/test_split_fn.py
   or: pytest tests/test_split_fn.py
"""

from database_undo import log_insertion, max_gap_split


class _FakeCursor:
    """Reports a fixed COUNT(*)"""

    def __init__(self, count):
        self._count = count

    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return (self._count,)

    def close(self):
        pass


class _FakeConn:
    """Always reports more rows in a box than the batch contains, so no box
    is ever exact and the splitter is always consulted."""

    def __init__(self, count=999):
        self._count = count

    def cursor(self):
        return _FakeCursor(self._count)

    def commit(self):
        pass


def _rows(n=40):
    return [dict(pk=i, x=i, y=i * 2, tag="A") for i in range(n)]


def _median_split(rows, varying_cols):
    """Cut the widest numeric column at its median.

    Shows the shape a replacement must have
    without reusing any of max_gap_split's logic.
    """
    best = None
    for col in varying_cols:
        vals = sorted(r[col] for r in rows if isinstance(r[col], (int, float)))
        if len(vals) < 2:
            continue
        span = vals[-1] - vals[0]
        if span and (best is None or span > best[0]):
            best = (span, col, vals[len(vals) // 2])
    return (best[1], best[2]) if best else (None, None)


def test_custom_split_fn_is_called():
    """A strategy passed as split_fn is consulted."""
    seen = []

    def recording_split(rows, varying_cols):
        seen.append(len(rows))
        return _median_split(rows, varying_cols)

    log_insertion(_FakeConn(), "t", _rows(), ["pk"], split_fn=recording_split)
    assert seen, "split_fn never called"


def test_default_does_not_call_the_custom_strategy():
    """Omitting split_fn uses max_gap_split"""
    seen = []

    def recording_split(rows, varying_cols):
        seen.append(len(rows))
        return _median_split(rows, varying_cols)

    log_insertion(_FakeConn(), "t", _rows(), ["pk"])
    assert not seen, "the default path called the custom strategy"


def test_declining_split_fn_falls_back_to_exception_ids():
    """A strategy that returns (None, None) must not lose rows: every row
    it declines to split has to come back as an explicit primary key."""
    rows = _rows()
    boxes, exception_ids = log_insertion(
        _FakeConn(), "t", rows, ["pk"], split_fn=lambda r, c: (None, None))
    assert not boxes, f"expected no boxes, got {len(boxes)}"
    assert len(exception_ids) == len(rows), (
        f"expected {len(rows)} exception ids, got {len(exception_ids)} "
        "-- rows were dropped")


def test_max_gap_split_is_the_default():
    """The documented default is the one in the signature."""
    import inspect
    sig = inspect.signature(log_insertion)
    assert sig.parameters["split_fn"].default is max_gap_split


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print()
    print("PASS: split_fn extension point verified" if not failures
          else f"FAIL: {failures} of {len(tests)} checks failed")
    raise SystemExit(1 if failures else 0)