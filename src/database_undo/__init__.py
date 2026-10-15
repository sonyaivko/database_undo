"""Storage-efficient undo for SQL INSERT and DELETE batches.
  
- **Bounding boxes** for undoing INSERTs. A batch of inserted rows is
  summarized as a set of predicate boxes. The undo is a
  `DELETE ... WHERE <box>` per box, plus an explicit primary-key list for
  rows no box could isolate. See :func:`log_insertion`.
 
- **Predict-and-patch** for undoing DELETEs. Columns determined by an
  approximate functional dependency are not stored raw. Only the
  predictor columns and a per-cell patch for each exception are stored. 
 
  * *global* (:func:`log_deletion`, :func:`undo_deletion`) mines FDs once
    over the whole table and resolves each dependency with a live `SELECT`
    at undo time. Correctness depends on the table's state at undo time.

  * *per-batch* (:func:`discover_rules`, :func:`log_batch_deletion`,
    :func:`undo_batch_deletion`) mines FDs from the deleted batch alone and
    stores the resulting value mapping in the log, so reconstruction reads
    no table at all.
 
Naive baselines for both mechanisms are exported for comparison.
"""
 
__version__ = "0.1.0"
 
from .db_config import conn_params, CONN_PARAMS
 
# INSERT undo
from .undo_lib import (
    log_insertion,
    undo_insertion,
    find_partitions,
    compute_dims,
    create_bounding_box,
    box_where_clause,
    count_in_box,
    contamination,
    max_gap_split,
    MIN_PROGRESS,
    CATEGORICAL_CARDINALITY_CAP,
)
 
# DELETE undo: global FDs
from .discover_fds import discover
from .fd_filter import load_csv_rows, filter_usable_fds, avg_group_size
from .fd_graph import build_dependency_graph
from .fd_patch_lib import log_deletion, undo_deletion, get_predictor_columns
 
# DELETE undo: per-batch FDs 
from .local_fd_discovery import discover_rules
from .local_fd_patch_lib import (
    topological_order,
    log_batch_deletion,
    undo_batch_deletion,
    undo_row,
)
 
# Naive baselines 
# Both baseline modules define `naive_storage_bytes`. 
# They are re-exported under distinct names.

from .naive_lib import (
    naive_log_insertion,
    naive_undo_insertion,
    naive_storage_bytes as naive_insert_storage_bytes,
)
from .naive_delete_lib import (
    naive_log_deletion,
    naive_undo_deletion,
    naive_undo_deletion_batch,
    naive_storage_bytes as naive_delete_storage_bytes,
)
 
# Generating test data 
from .tpcc_rows import make_customer_row
from .tpcc_gen import (
    gen_warehouses,
    gen_districts,
    gen_items,
    gen_customers,
    load,
)
 
__all__ = [
    "__version__",
    # configuration
    "conn_params",
    "CONN_PARAMS",
    # INSERT undo
    "log_insertion",
    "undo_insertion",
    "find_partitions",
    "compute_dims",
    "create_bounding_box",
    "box_where_clause",
    "count_in_box",
    "contamination",
    "max_gap_split",
    "MIN_PROGRESS",
    "CATEGORICAL_CARDINALITY_CAP",
    # DELETE undo, global FDs
    "discover",
    "load_csv_rows",
    "filter_usable_fds",
    "avg_group_size",
    "build_dependency_graph",
    "log_deletion",
    "undo_deletion",
    "get_predictor_columns",
    # DELETE undo, per-batch FDs
    "discover_rules",
    "topological_order",
    "log_batch_deletion",
    "undo_batch_deletion",
    "undo_row",
    # naive baselines
    "naive_log_insertion",
    "naive_undo_insertion",
    "naive_insert_storage_bytes",
    "naive_log_deletion",
    "naive_undo_deletion",
    "naive_undo_deletion_batch",
    "naive_delete_storage_bytes",
    # test data generation
    "make_customer_row",
    "gen_warehouses",
    "gen_districts",
    "gen_items",
    "gen_customers",
    "load",
]
 