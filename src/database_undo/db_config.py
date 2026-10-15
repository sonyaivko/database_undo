"""
Run against a local Postgres, a container, or a remote host:

    export UNDO_DB_HOST=localhost
    export UNDO_DB_PORT=5432
    export UNDO_DB_NAME=undo_test
    export UNDO_DB_USER=undo_user
    export UNDO_DB_PASSWORD=undo_pass

`CONN_PARAMS` is read once at import time. Call `conn_params()` instead if
you need to pick up an environment change made after import, or to override
one field for a single connection.
"""

import os

DEFAULTS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "undo_test",
    "user": "undo_user",
    "password": "undo_pass",
}

_ENV_VARS = {
    "host": "UNDO_DB_HOST",
    "port": "UNDO_DB_PORT",
    "dbname": "UNDO_DB_NAME",
    "user": "UNDO_DB_USER",
    "password": "UNDO_DB_PASSWORD",
}


def conn_params(**overrides):
    """Returns psycopg2 connection keywords, as a dict.

    Each field is taken from its environment variable if set, otherwise from
    `DEFAULTS`. 

    - `overrides`: connection keywords to force, e.g. `dbname="scratch"`.
    - Returns: a dict suitable for `psycopg2.connect(**...)`.
    - Raises: `ValueError` if `UNDO_DB_PORT` is set to something non-numeric.
    """
    params = {}
    for key, default in DEFAULTS.items():
        value = os.environ.get(_ENV_VARS[key], default)
        if key == "port":
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"{_ENV_VARS[key]}={value!r} is not a valid port number"
                )
        params[key] = value
    params.update(overrides)
    return params


CONN_PARAMS = conn_params()