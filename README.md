## Usage
 
Two mechanisms are in use: **bounding boxes** for undoing INSERTs (steps
3–5) and **per-batch predict-and-patch** for undoing DELETEs (step 6). Step
7 is an optional comparison using a black-box algorithm.

Step 1 requires the install, the rest need PostgreSQL. 
 
### CLI
 
#### 1. Confirm the install
 
```console
$ python3 tests/test_split_fn.py
PASS  test_custom_split_fn_is_called
PASS  test_declining_split_fn_falls_back_to_exception_ids
PASS  test_default_does_not_call_the_custom_strategy
PASS  test_max_gap_split_is_the_default
 
PASS: split_fn extension point verified
```
 
#### 2. Start a database

If you already have a server, skip this and use the variables
in [Environment](#environment). If port 5432 is taken, see
[Troubleshooting](#troubleshooting).
 
```console
$ docker run --name undo-postgres \
    -e POSTGRES_USER=undo_user -e POSTGRES_PASSWORD=undo_pass \
    -e POSTGRES_DB=undo_test -p 5432:5432 -d postgres:16
$ until docker exec undo-postgres pg_isready -U undo_user -d undo_test; do sleep 1; done
/var/run/postgresql:5432 - accepting connections
$ docker exec -i undo-postgres psql -U undo_user -d undo_test < schema/tpcc_postgres.sql
$ dbundo-load-tpcc
Generating + loading WAREHOUSE...
...
WAREHOUSE 2
DISTRICT 20
ITEM 1000
CUSTOMER 6000
```
 
#### 3. Undo a batch of INSERTs
 
```console
$ python3 tests/test_correctness.py
TEST 1: insert with no pre-existing rows -> should be one pure box
batch size=40  boxes=1  exceptions=0
  box storage: 353 bytes  |  naive ID-list storage: 511 bytes  |  ratio: 0.69x
before undo: 40 rows, deleted: 40, after undo: 0 rows
PASS: exact rollback, district 11 empty again
 
TEST 2: insert into EXISTING district (w=1,d=5 already has c_id 1..300)
batch size=40  boxes=1  exceptions=0
  box storage: 355 bytes  |  naive ID-list storage: 520 bytes  |  ratio: 0.68x
district 6 (control, must be untouched): before=300, after=300
PASS: exact rollback, no collateral damage to district 6
```
 
#### 4. Run the comparison of leaf sizes
 
```console
$ python3 experiments/leaf_size_sweep.py
size=  10  boxes=0 exc=10  box_bytes=2  naive_bytes=126  ratio=N/A (below numDims threshold)
size=  15  boxes=1 exc=0  box_bytes=352  naive_bytes=195  ratio=1.805x
size=  25  boxes=1 exc=0  box_bytes=351  naive_bytes=325  ratio=1.080x
size=  30  boxes=1 exc=0  box_bytes=352  naive_bytes=419  ratio=0.840x
size= 100  boxes=1 exc=0  box_bytes=354  naive_bytes=1400  ratio=0.253x
```
 
`box_bytes` is flat at 351–354 while `naive_bytes` grows ~13 bytes per
row — one box is one set of bounds however many rows fall inside. The curves
cross between 25 and 30 rows. 
 
#### 5. Reproduce the insert experiment
 
```console
$ python3 experiments/sweep_insert.py
Populating dense old data (1..123000)...
batch=   10 trial=0  boxes=0 (expected 2) exc=10  storage ratio=1.012x  log_time ratio=5.20x  [MISMATCH]
batch=   25 trial=0  boxes=2 (expected 2) exc=0  storage ratio=1.649x  log_time ratio=2383.68x  [OK]
batch=  100 trial=0  boxes=2 (expected 2) exc=0  storage ratio=0.414x  log_time ratio=679.19x  [OK]
...
batch= 2000 trial=0  boxes=2 (expected 2) exc=0  storage ratio=0.020x  log_time ratio=30.40x  [OK]
 
Wrote 40 rows to <repo>/results/insert_sweep_results.csv
 
WARNING: 5 trial(s) did not produce the expected 2-box, 0-exception split
```
 
At 2000 rows the log is 50x smaller.
 
The `WARNING` is expected. 
 
```console
$ python3 experiments/plot_insert.py
saved <repo>/results/insert_sweep_plot.png
```
 
#### 6. Undo DELETEs- per-batch dependencies
 
Mines dependencies from the deleted rows. Start by asking what is compressible:
 
```console
$ python3 experiments/inspect_rules.py customer 1000 c_w_id c_d_id c_id
 1. c_credit_lim         <- (constant)                saved=  7000 bytes  coverage=1.000  likely_real=True
 2. c_balance            <- (constant)                saved=  5000 bytes  coverage=1.000  likely_real=True
 ...
 6. c_credit             <- c_middle                  saved=  2012 bytes  coverage=0.503  likely_real=False
 ...
Wrote <repo>/results/rule_bytes_saved_customer.csv
```
 
```console
$ python3 experiments/sweep_local_fd_delete.py customer c_w_id c_d_id c_id
batch=    5 trial=0  storage ratio=0.392x  discovery=1.4ms log=0.04ms undo=4.64ms  plain_delete=4.00ms  ruled=7 (likely_real=7) predictors=11
batch=  100 trial=0  storage ratio=0.358x  discovery=51.7ms log=0.53ms undo=59.98ms  plain_delete=45.33ms  ruled=8 (likely_real=7) predictors=10
...
batch= 1000 trial=0  storage ratio=0.356x  discovery=173.5ms log=5.20ms undo=559.88ms  plain_delete=418.46ms  ruled=8 (likely_real=7) predictors=10
 
Wrote 24 rows to <repo>/results/local_fd_sweep_results_customer.csv
```
 
#### 7. Optional: the global-FD path, for comparison
 
An earlier approach, kept so the difference can be measured. It mines
dependencies from a whole table once using [Desbordante][desbordante], then
resolves them with a live query at undo time.
 
**This is not the design any more.** It puts dependency discovery inside 
an external solver (Desbordante) we treat as a black box, and the measurements below
show it increasing runtime by orders of magnitude. 
 
It needs a CSV export and the `discovery` extra.
 
[desbordante]: https://github.com/Desbordante/desbordante-core
 
```console
$ docker exec -i undo-postgres psql -U undo_user -d undo_test \
    -c "\copy customer TO STDOUT WITH CSV HEADER" > customer.csv
$ dbundo-discover-fds customer.csv c_w_id c_d_id c_id
176 raw FDs -> 7 usable after filtering (PK excluded: ['c_w_id', 'c_d_id', 'c_id'])
 
  [] -> c_middle   (avg group size: 6000.0)
  [] -> c_state   (avg group size: 6000.0)
  ...
Wrote customer_fds.json
```
 
169 of 176 dependency candidates are discarded. All seven survivors 
have an empty left-hand side over one group of 6000 rows, i.e. they are constants.
 
```console
$ python3 tests/test_fd_patch.py customer_fds.json customer c_w_id c_d_id c_id --limit 5
Topo order: ['c_middle', 'c_state', 'c_credit_lim', 'c_balance', 'c_ytd_payment', 'c_payment_cnt', 'c_delivery_cnt']
  row {'c_w_id': 2, 'c_d_id': 10, 'c_id': 121}: 11 predictors stored, 0 fdPatch overrides ([])
  ...
  row {'c_w_id': 2, 'c_d_id': 10, 'c_id': 121}: EXACT MATCH
  ...
PASS: all reconstructed rows exactly match originals
```

 
```console
$ python3 experiments/sweep_delete.py customer_fds.json customer c_w_id c_d_id c_id
batch=    5 trial=0  storage ratio=0.658x  log_time ratio=8871.88x  undo_time ratio=9.58x
batch=   50 trial=0  storage ratio=0.656x  log_time ratio=95563.59x  undo_time ratio=9.29x
batch=  100 trial=0  storage ratio=0.657x  log_time ratio=151988.78x  undo_time ratio=10.96x
```
 
See [Known limitations](#known-limitations).
 
### Troubleshooting
 
| symptom | cause and fix |
|---|---|
| `ModuleNotFoundError: psycopg2` | virtualenv not active — `source .venv/bin/activate` |
| `ModuleNotFoundError: pandas` | `pip install -e '.[plots]'` — quote the brackets in zsh |
| `bind: address already in use` on 5432 | another PostgreSQL. `sudo lsof -iTCP:5432 -sTCP:LISTEN` to find it; or map `-p 5433:5432` and `export UNDO_DB_PORT=5433` in every terminal |
| `ValueError: UNDO_DB_PORT=... is not a valid port` | malformed variable. Fires on **import**, not connect, since `CONN_PARAMS` is built at module level |
| `could not connect to server` | wrong target, or the container is not ready yet. Print the target with `python3 -c "from database_undo import conn_params; print(conn_params())"` |
| `FileNotFoundError` from a plot | run the matching sweep first. `plot_insert.py` needs **both** `sweep_insert.py` and `leaf_size_sweep.py` |
 
`ValueError: Cannot reconstruct column ...` from `undo_deletion` is not a
bug — it is the live-table dependency of the superseded path. See
[Known limitations](#known-limitations).
 
### Environment
 
Connection settings come from the environment with these defaults.
 
| variable | default |
|---|---|
| `UNDO_DB_HOST` | `localhost` |
| `UNDO_DB_PORT` | `5432` |
| `UNDO_DB_NAME` | `undo_test` |
| `UNDO_DB_USER` | `undo_user` |
| `UNDO_DB_PASSWORD` | `undo_pass` |
 
```console
$ UNDO_DB_NAME=scratch python3 -c "from database_undo import conn_params; print(conn_params()['dbname'])"
scratch
```
 
### Files
 
Sweeps write CSVs and plots write PNGs to `results/`. 
`dbundo-discover-fds` writes `<csv>_fds.json`. 
`results/` is gitignored.
 
---
 
## API
 
40 names are exported. 
 
### `log_insertion(conn, table, batch_rows, pk_cols, split_fn=max_gap_split)`
 
Summarises an inserted batch as bounding boxes plus keys for exceptions.
Call after the insert, before the undo. Reads only.
 
- `table` (str), `batch_rows` (list of dict, keyed by column name),
  `pk_cols` (list of str).
- `split_fn` (callable, optional): the splitting strategy and this module's
  extension point.
- Returns: `(boxes, exception_ids)`. A box is
  `{"eq": {col: value}, "range": {col: (lo, hi)}, "set": {col: {values}}}`;
  `exception_ids` is a list of primary-key tuples.
Every box is exact. Below roughly 27 rows it returns no boxes and puts every row
in `exception_ids`.
 
### `undo_insertion(conn, table, boxes, exception_ids, pk_cols)`
 
One `DELETE ... WHERE <box>` per box, plus one for the exception keys.
Commits.
 
- Returns: `int` rows deleted — compare with your batch size.
```python
from database_undo import log_insertion, undo_insertion
 
pk_cols = ["c_w_id", "c_d_id", "c_id"]
boxes, exceptions = log_insertion(conn, "customer", batch, pk_cols)
deleted = undo_insertion(conn, "customer", boxes, exceptions, pk_cols)
assert deleted == len(batch)
```
 
### `discover_rules(batch_rows, pk_cols, **tuning)`
 
Approximate functional dependencies within one batch, by greedily growing a
predictor set per target column.
 
- `batch_rows` (list of dict), `pk_cols` (list of str).
- Tuning: `sample_size=300`, `min_group_size=20.0`,
  `min_coverage_to_accept=0.5`, `target_coverage=0.8`,
  `baseline_margin_for_confidence=0.1`, `constant_threshold=0.98`,
  `max_predictors=4`.
- Returns: `{target: rule}`, where a rule holds `source` (predictor columns,
  `[]` for a constant), `mapping` (predictor tuple → value), `coverage`,
  `baseline`, `likely_real`, `rows_free`, `rows_patched`, `bytes_saved`,
  `bytes_still_needed`. `{}` for an empty batch. 
`likely_real` is a label, not a filter: a rule marked `False` is still
returned and used. It flags rules that barely beat guessing the most common
value.
 
### `log_batch_deletion(batch_rows, pk_cols, rules)`
 
- Returns: `(deleted_log, fd_patch)`, keyed by primary-key tuple.
  `deleted_log[pk]` holds uncovered columns; `fd_patch[pk]` holds only cells
  a rule gets wrong. 
### `undo_batch_deletion(conn, table, pk_cols, deleted_log, fd_patch, rules, topo_order)`
 
Reconstructs and re-inserts every logged row and commits.
 
- `topo_order`: from `topological_order(rules)`
- Returns: `int` rows inserted.
- Raises: `ValueError` if a rule has no mapping entry for a row and no patch
  supplies the cell.
```python
from database_undo import (
    discover_rules, topological_order,
    log_batch_deletion, undo_batch_deletion,
)
 
rules = discover_rules(victims, pk_cols)
deleted_log, fd_patch = log_batch_deletion(victims, pk_cols, rules)
#the DELETE happens here 
n = undo_batch_deletion(conn, "customer", pk_cols, deleted_log, fd_patch,
                        rules, topological_order(rules))
```
 
### Optional: Desbordante global-FD path
 
The two functions below belong to the earlier whole-table approach described
in [Usage step 7](#7-optional-the-global-fd-path-for-comparison). They work
and are exported, but they are not the recommended path.
 
#### `log_deletion(conn, table, row, pk_cols, rules, batch_pks=None)`
 
The global path's logger.
 
- `row` (dict): the full row before the delete.
- `rules`: `{column: (lhs_cols, avg_group_size)}` from
  `build_dependency_graph`.
- `batch_pks` (list of dict, optional): every primary key in the batch.
- Returns: `(predictors, fd_patch)`.
 
#### `undo_deletion(conn, table, pk_vals, predictors, fd_patch, rules, topo_order)`
 
Reconstructs one row and inserts it if absent and commits.
 
- Returns: `(reconstructed, existed_already)`.
- Raises: `ValueError` if no row shares a column's predictor
  values and there is no overriding patch.