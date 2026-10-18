## Usage
 
Everything runs from a terminal. Step 1 needs the installed package,
steps 2 onward need a running PostgreSQL.
 
If a command fails, run it with no arguments — every script prints its own
usage. Common problems are collected in [Troubleshooting](#troubleshooting).
 
### CLI
 
One check runs without a database. It drives the bounding-box splitter
against a stubbed connection:
 
```console
$ python3 tests/test_split_fn.py
PASS  test_custom_split_fn_is_called
PASS  test_declining_split_fn_falls_back_to_exception_ids
PASS  test_default_does_not_call_the_custom_strategy
PASS  test_max_gap_split_is_the_default
 
PASS: split_fn extension point verified
```
 
If this passes, the package is installed.
 
#### 2. Start a database
 
The defaults expect a database `undo_test` owned by `undo_user` on
`localhost:5432`. You can use Docker to set this:
 
```console
$ docker run --name undo-postgres \
    -e POSTGRES_USER=undo_user \
    -e POSTGRES_PASSWORD=undo_pass \
    -e POSTGRES_DB=undo_test \
    -p 5432:5432 -d postgres:16
```
 
[CAPTURE: docker prints a container id]
 
Wait a few seconds for it to accept connections, then load the schema and
generate a small TPC-C dataset:
 
```console
$ docker exec -i undo-postgres psql -U undo_user -d undo_test < schema/tpcc_postgres.sql
$ dbundo-load-tpcc
```
 
[CAPTURE: "Generating + loading WAREHOUSE..." etc, then one count per table.
From the constants in tpcc_gen.py this should be WAREHOUSE 2, DISTRICT 20,
ITEM 1000, CUSTOMER 6000 — confirm before publishing.]
 
##### If you already have PostgreSQL running
Skip all of this and point the package at
it with the variables in [Environment](#environment) instead.
 