"""Require the qualified PostgreSQL transaction mode before application or queue writes."""

import psycopg
from sqlalchemy.engine import Connection


# Reject unsupported drivers, autocommit and isolation before the first write.
#
# Concurrent ON CONFLICT followed by lookup is qualified under READ COMMITTED. This guard
# fails closed rather than silently changing caller isolation or committing a raw connection.
def require_transaction(connection: Connection) -> psycopg.Connection:
    raw = connection.connection.driver_connection
    if (
        not connection.in_transaction()
        or not isinstance(raw, psycopg.Connection)
        or raw.autocommit
        or connection.get_isolation_level() != "READ COMMITTED"
    ):
        raise RuntimeError("ACTIVE_READ_COMMITTED_PSYCOPG_TRANSACTION_REQUIRED")
    return raw
