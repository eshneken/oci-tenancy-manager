"""Run migrations only on an explicitly supplied migration-owner connection, never a saved URL."""

from alembic import context

from otm.storage.tables import metadata


# Require external connection ownership and transactional DDL; runtime API never calls this.
def run() -> None:
    connection = context.config.attributes.get("connection")
    if connection is None or context.is_offline_mode():
        raise RuntimeError(
            "Provide an explicit migration connection; no default database is allowed"
        )
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table_schema="public",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run()
