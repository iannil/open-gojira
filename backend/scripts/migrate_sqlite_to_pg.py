#!/usr/bin/env python3
"""One-time migration: SQLite → PostgreSQL.

Reads all data from the existing SQLite database and writes it to PostgreSQL.
Designed to run once after switching from SQLite to PG.

Usage:
    # Default: read SQLite from backend/data/gojira.db, write to config's DATABASE_URL
    python backend/scripts/migrate_sqlite_to_pg.py

    # Explicit paths:
    SQLITE_PATH=/path/to/gojira.db DATABASE_URL=postgresql://u:p@h:port/db \\
        python backend/scripts/migrate_sqlite_to_pg.py

Safe to re-run — skips tables that already have data in PG.
"""

import logging
import os
import sys
from collections import defaultdict, deque
from pathlib import Path

# Ensure backend/ is on sys.path so app.config imports work
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrate")

# ── Config ──────────────────────────────────────────────────────────────────
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH", _BACKEND / "data" / "gojira.db"))
PG_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://gojira:gojira@localhost:5432/gojira",
)

# Tables that should be skipped (system/internal)
SKIP_TABLES: set[str] = {"alembic_version", "spatial_ref_sys"}

# Large data tables that can be re-synced from Lixinger API (skip for speed)
# These will be re-populated by the scheduler's data sync pipelines.
REFRESH_FROM_API: set[str] = {
    "index_klines",
}

# Tables we know have no data / are safe to always re-migrate
FORCE_REPLACE: set[str] = set()

# Parent tables that must be migrated before any dependents
# (needed when FK constraints exist in PG models but not in SQLite metadata)
PARENT_TABLES: list[str] = ["stocks"]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _topological_sort(tables: list[str], inspector) -> list[str]:
    """Order tables so that FK parents come before their dependents."""
    # Ensure critical parent tables are first
    result: list[str] = [t for t in PARENT_TABLES if t in tables]
    remaining = [t for t in tables if t not in result]

    # Build adjacency: child → [parents]"
    # Build adjacency: child → [parents]
    graph: dict[str, set[str]] = {t: set() for t in remaining}
    for table in remaining:
        for fk in inspector.get_foreign_keys(table):
            parent = fk["referred_table"]
            if parent in graph:
                graph[table].add(parent)

    # Kahn's algorithm (topological sort — parent-first)
    in_degree: dict[str, int] = {t: len(deps) for t, deps in graph.items()}
    queue: deque[str] = deque(t for t, d in in_degree.items() if d == 0)
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child, parents in graph.items():
            if node in parents:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

    # Append any cycles (unlikely) at the end
    remaining = [t for t in tables if t not in result and t not in ordered]
    return result + ordered + remaining


def _reset_sequences(pg_session: Session, inspector) -> None:
    """Reset PG sequences to max(id)+1 for each table with an auto-increment PK."""
    for table in inspector.get_table_names():
        if table in SKIP_TABLES:
            continue
        pk_cols = inspector.get_pk_constraint(table).get("constrained_columns", [])
        if len(pk_cols) != 1:
            continue
        pk = pk_cols[0]
        # Only reset for integer primary keys (serial/bigserial)
        col_info = [c for c in inspector.get_columns(table) if c["name"] == pk]
        if not col_info:
            continue
        col_type = str(col_info[0].get("type", "")).lower()
        if not any(t in col_type for t in ("int", "serial")):
            continue

        seq_name = f"{table}_{pk}_seq"
        try:
            pg_session.execute(
                text(
                    f"SELECT setval('{seq_name}', "
                    f"COALESCE((SELECT MAX({pk}) FROM {table}), 0) + 1, false)"
                )
            )
        except Exception:
            # sequence may not exist yet (empty table, or not serial)
            pass


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    sqlite_url = f"sqlite:///{SQLITE_PATH.resolve()}"
    logger.info("Source:      %s", sqlite_url)
    logger.info("Target:      %s", PG_URL.split("@")[-1] if "@" in PG_URL else PG_URL)

    if not SQLITE_PATH.exists():
        logger.error("SQLite database not found at %s", SQLITE_PATH)
        return 1

    # ── Connect ─────────────────────────────────────────────────────────────
    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    pg_engine = create_engine(PG_URL)

    # ── Create tables in PG if they don't exist ─────────────────────────────
    # Import all models so they register with Base.metadata
    from app.db.base import Base as AppBase
    import app.models  # noqa: F401  — register every model on Base.metadata
    AppBase.metadata.create_all(bind=pg_engine)
    logger.info("Ensured all tables exist in PostgreSQL")

    sqlite_inspector = inspect(sqlite_engine)
    pg_inspector = inspect(pg_engine)

    # Discover tables from SQLite (source of truth for what to migrate)
    source_tables = [
        t
        for t in sqlite_inspector.get_table_names()
        if t not in SKIP_TABLES
    ]
    ordered_tables = _topological_sort(source_tables, sqlite_inspector)

    logger.info("Discovered %d tables to migrate (FK-sorted)", len(ordered_tables))

    stats: dict[str, int] = {}

    with pg_engine.connect() as pg_conn:
        pg_conn.execution_options(isolation_level="AUTOCOMMIT")

        for table_name in ordered_tables:
            # ── Skip large data tables (re-sync from API instead) ──────────
            if table_name in REFRESH_FROM_API:
                logger.info("  %-30s  SKIP — re-sync from Lixinger API", table_name)
                stats[table_name] = 0
                continue

            # ── Check if already migrated ───────────────────────────────────
            pg_exists = table_name in pg_inspector.get_table_names()
            if not pg_exists:
                logger.warning("  Table '%s' does not exist in PG — skipping", table_name)
                continue

            if table_name not in FORCE_REPLACE:
                existing_count = (
                    pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                    or 0
                )
                if existing_count > 0:
                    logger.info(
                        "  %-30s  SKIP — already has %d rows", table_name, existing_count
                    )
                    stats[table_name] = existing_count
                    continue

            # ── Read from SQLite ────────────────────────────────────────────
            with sqlite_engine.connect() as sqlite_conn:
                result = sqlite_conn.execute(
                    text(f'SELECT * FROM "{table_name}"')
                )
                col_names = list(result.keys())  # get column names from Result, not Row
                rows = result.fetchall()

            if not rows:
                logger.info("  %-30s  EMPTY", table_name)
                stats[table_name] = 0
                continue

            # ── Get PG column types for type coercion ───────────────────────
            pg_col_types: dict[str, str] = {}
            for c in pg_inspector.get_columns(table_name):
                pg_col_types[c["name"]] = str(c["type"]).lower()

            def _coerce(val, col_type: str):
                """Convert SQLite int 0/1 → bool for PG boolean columns."""
                if "bool" in col_type and isinstance(val, int):
                    return bool(val)
                return val

            # ── Build insert values with type coercion ──────────────────────
            values_batch = [
                {
                    col: _coerce(row._mapping[col], pg_col_types.get(col, ""))
                    for col in col_names
                }
                for row in rows
            ]

            placeholders = ", ".join(f":{c}" for c in col_names)
            columns_fmt = ", ".join(f'"{c}"' for c in col_names)

            # ── Batch insert ────────────────────────────────────────────────
            BATCH_SIZE = 500
            total = 0
            for i in range(0, len(values_batch), BATCH_SIZE):
                batch = values_batch[i : i + BATCH_SIZE]
                pg_conn.execute(
                    text(
                        f'INSERT INTO "{table_name}" ({columns_fmt}) '
                        f"VALUES ({placeholders}) "
                        f"ON CONFLICT DO NOTHING"
                    ),
                    batch,
                )
                total += len(batch)

            # ── Reset sequence ──────────────────────────────────────────────
            pk_cols = sqlite_inspector.get_pk_constraint(table_name).get(
                "constrained_columns", []
            )
            if len(pk_cols) == 1:
                pk = pk_cols[0]
                col_info = [
                    c for c in sqlite_inspector.get_columns(table_name) if c["name"] == pk
                ]
                if col_info:
                    col_type = str(col_info[0].get("type", "")).lower()
                    if any(t in col_type for t in ("integer", "int")):
                        seq_name = f"{table_name}_{pk}_seq"
                        try:
                            pg_conn.execute(
                                text(
                                    f"SELECT setval('{seq_name}', "
                                    f"COALESCE((SELECT MAX({pk}) FROM \"{table_name}\"), 0) + 1, false)"
                                )
                            )
                        except Exception:
                            pass

            stats[table_name] = total
            logger.info(
                "  %-30s  %s rows migrated",
                table_name,
                total,
            )

    pg_engine.dispose()
    sqlite_engine.dispose()

    # ── Summary ─────────────────────────────────────────────────────────────
    total_rows = sum(stats.values())
    # Only count freshly migrated rows
    fresh_rows = sum(
        c for t, c in stats.items() if t not in [k for k, v in stats.items() if c == 0]
    )
    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration complete")
    logger.info("  Tables processed: %d", len(stats))
    logger.info("  Total rows:       %d", total_rows)
    logger.info("  Freshly migrated: %d", fresh_rows)
    logger.info("")
    logger.info("NOTE: If any rows were skipped (already existed), they were left untouched.")
    logger.info("      To force a re-migrate, add table names to FORCE_REPLACE in this script.")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
