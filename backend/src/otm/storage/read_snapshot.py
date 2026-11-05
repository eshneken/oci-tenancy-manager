"""Short coherent read transactions for directories updated by independent workers."""

from contextlib import contextmanager


# Keep totals/rows and status/history coherent without acquiring application write locks.
@contextmanager
def read_snapshot(engine):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            yield connection
