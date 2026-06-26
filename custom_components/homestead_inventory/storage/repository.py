"""SQLite-backed storage for Homestead Inventory.

Design goals (the "safety" half of the merge):

* A single persistent ``aiosqlite`` connection, opened on the event loop.
* Every database operation is serialized behind one ``asyncio.Lock`` so a
  read can never interleave with another write's transaction on the shared
  connection. A home inventory has trivial concurrency; correctness wins.
* ``PRAGMA foreign_keys = ON`` on every connection so the ``ON DELETE
  CASCADE`` constraints actually fire (the original Home Inventory left this
  off, silently orphaning children when a room/cupboard/shelf was deleted).
* WAL + ``synchronous = NORMAL`` + ``busy_timeout`` for durability without
  "database is locked" errors under the 1-minute sensor polling.
* Explicit schema versioning + migrations so user data survives upgrades.

The repository is storage-only: it returns the *filenames* of images that
should be removed from disk, but never touches the filesystem itself. The
caller (the image helper) owns that.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# Unique sentinel for "argument not supplied" — avoids colliding with any real
# value a caller might pass (a magic string could).
_UNSET = object()


def _as_int_or_none(value: Any) -> int | None:
    """Coerce a quantity to int (or None), so non-int values can't be stored
    verbatim into an INTEGER column. Raises ValueError on non-numeric input."""
    return None if value is None else int(value)


class InventoryRepository:
    """Async SQLite repository for the room/cupboard/shelf/organizer/item tree."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def async_initialize(self) -> None:
        """Open the connection, apply pragmas, ensure schema + migrations.

        Uses autocommit (isolation_level=None) so a failed single write never
        leaves a dangling transaction on this long-lived connection. The few
        multi-statement operations that need atomicity use _transaction().
        """
        async with self._lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self._db_path, isolation_level=None)
            try:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA foreign_keys = ON")
                await conn.execute("PRAGMA journal_mode = WAL")
                await conn.execute("PRAGMA synchronous = NORMAL")
                await conn.execute("PRAGMA busy_timeout = 5000")
                self._conn = conn
                await self._create_schema()
                await self._run_migrations()
            except BaseException:
                # Never leave a half-open connection that a retry would treat
                # as "ready" (the guard above short-circuits on non-None).
                self._conn = None
                with contextlib.suppress(Exception):
                    await conn.close()
                raise
            _LOGGER.debug("Homestead Inventory DB ready at %s", self._db_path)

    async def async_close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    def _c(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("InventoryRepository not initialized")
        return self._conn

    @contextlib.asynccontextmanager
    async def _transaction(self):
        """Explicit multi-statement transaction (the connection is autocommit).

        Commits on success, rolls back on any error so a partial multi-write
        operation can never be left half-applied.
        """
        conn = self._c()
        await conn.execute("BEGIN")
        try:
            yield conn
            await conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(Exception):
                await conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------ #
    # Schema / migrations  (callers already hold the lock)
    # ------------------------------------------------------------------ #

    async def _create_schema(self) -> None:
        conn = self._c()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL COLLATE NOCASE UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cupboards (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL COLLATE NOCASE,
                image      TEXT,
                room_id    INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                UNIQUE (name, room_id)
            );

            CREATE TABLE IF NOT EXISTS shelves (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL COLLATE NOCASE,
                cupboard_id INTEGER NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cupboard_id) REFERENCES cupboards(id) ON DELETE CASCADE,
                UNIQUE (name, cupboard_id)
            );

            CREATE TABLE IF NOT EXISTS organizers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL COLLATE NOCASE,
                image      TEXT,
                shelf_id   INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shelf_id) REFERENCES shelves(id) ON DELETE CASCADE,
                UNIQUE (name, shelf_id)
            );

            CREATE TABLE IF NOT EXISTS items (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                aliases        TEXT,
                barcode        TEXT,
                image          TEXT,
                shelf_id       INTEGER NOT NULL,
                organizer_id   INTEGER DEFAULT NULL,
                quantity       INTEGER DEFAULT NULL,
                min_quantity   INTEGER DEFAULT NULL,
                track_quantity INTEGER NOT NULL DEFAULT 0,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shelf_id) REFERENCES shelves(id) ON DELETE CASCADE,
                FOREIGN KEY (organizer_id) REFERENCES organizers(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_cupboards_room      ON cupboards(room_id);
            CREATE INDEX IF NOT EXISTS idx_shelves_cupboard    ON shelves(cupboard_id);
            CREATE INDEX IF NOT EXISTS idx_organizers_shelf    ON organizers(shelf_id);
            CREATE INDEX IF NOT EXISTS idx_items_shelf         ON items(shelf_id);
            CREATE INDEX IF NOT EXISTS idx_items_organizer     ON items(organizer_id);
            CREATE INDEX IF NOT EXISTS idx_items_quantity      ON items(quantity);
            """
        )

    async def _run_migrations(self) -> None:
        conn = self._c()
        cur = await conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        row = await cur.fetchone()
        await cur.close()

        if row is None:
            # Fresh DB created at the current schema; ensure derived objects exist.
            await self._migrate_v2()
            await conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            return

        try:
            current = int(row[0])
        except (TypeError, ValueError) as err:
            raise RuntimeError(
                f"Homestead Inventory DB has a corrupt schema_version: {row[0]!r}"
            ) from err
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Homestead Inventory DB schema v{current} is newer than this "
                f"integration supports (v{SCHEMA_VERSION}). Update the integration."
            )
        if current < 2:
            await self._migrate_v2()
        if current != SCHEMA_VERSION:
            await conn.execute(
                "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
                (str(SCHEMA_VERSION),),
            )

    async def _migrate_v2(self) -> None:
        """v1 -> v2: add items.barcode + its index. Idempotent (safe on a fresh
        DB where the column already exists, and on re-runs)."""
        conn = self._c()
        with contextlib.suppress(Exception):
            await conn.execute("ALTER TABLE items ADD COLUMN barcode TEXT")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode)"
        )

    # ------------------------------------------------------------------ #
    # Internal resolvers (callers already hold the lock + use the cursor)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _resolve_shelf_id(cur, room: str, cupboard: str, shelf: str) -> int | None:
        await cur.execute(
            """
            SELECT s.id FROM shelves s
            JOIN cupboards c ON s.cupboard_id = c.id
            JOIN rooms r ON c.room_id = r.id
            WHERE r.name = ? AND c.name = ? AND s.name = ?
            """,
            (room, cupboard, shelf),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    @staticmethod
    async def _resolve_organizer_id(
        cur, room: str, cupboard: str, shelf: str, organizer: str
    ) -> int | None:
        await cur.execute(
            """
            SELECT o.id FROM organizers o
            JOIN shelves s ON o.shelf_id = s.id
            JOIN cupboards c ON s.cupboard_id = c.id
            JOIN rooms r ON c.room_id = r.id
            WHERE r.name = ? AND c.name = ? AND s.name = ? AND o.name = ?
            """,
            (room, cupboard, shelf, organizer),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------ #
    # Rooms
    # ------------------------------------------------------------------ #

    async def list_rooms(self) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT r.id, r.name, COUNT(DISTINCT i.id) AS item_count
                FROM rooms r
                LEFT JOIN cupboards c ON r.id = c.room_id
                LEFT JOIN shelves s ON c.id = s.cupboard_id
                LEFT JOIN items i ON s.id = i.shelf_id
                GROUP BY r.id, r.name
                ORDER BY r.name COLLATE NOCASE
                """
            )
            rows = await cur.fetchall()
            await cur.close()
        return [{"id": r[0], "name": r[1], "itemCount": r[2]} for r in rows]

    async def create_room(self, name: str) -> int:
        async with self._lock:
            cur = await self._c().execute("INSERT INTO rooms (name) VALUES (?)", (name,))
            await self._c().commit()
            return cur.lastrowid

    async def update_room(self, room_id: int, name: str) -> int:
        async with self._lock:
            cur = await self._c().execute(
                "UPDATE rooms SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, room_id),
            )
            await self._c().commit()
            return cur.rowcount

    async def delete_room(self, room_id: int) -> tuple[int, list[str]]:
        """Delete a room; FK cascade removes children. Returns (count, image filenames)."""
        async with self._lock:
            conn = self._c()
            images: list[str] = []
            cur = await conn.execute(
                "SELECT image FROM cupboards WHERE room_id = ? AND image IS NOT NULL AND image != ''",
                (room_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute(
                """
                SELECT i.image FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                WHERE c.room_id = ? AND i.image IS NOT NULL AND i.image != ''
                """,
                (room_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute("SELECT o.image FROM organizers o "
                                     "JOIN shelves s ON o.shelf_id = s.id "
                                     "JOIN cupboards c ON s.cupboard_id = c.id "
                                     "WHERE c.room_id = ? AND o.image IS NOT NULL AND o.image != ''",
                                     (room_id,))
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            await conn.commit()
            return cur.rowcount, images

    # ------------------------------------------------------------------ #
    # Cupboards
    # ------------------------------------------------------------------ #

    async def list_cupboards(self, room: str) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT c.id, c.name, c.image, COUNT(DISTINCT i.id) AS item_count
                FROM cupboards c
                JOIN rooms r ON c.room_id = r.id
                LEFT JOIN shelves s ON c.id = s.cupboard_id
                LEFT JOIN items i ON s.id = i.shelf_id
                WHERE r.name = ?
                GROUP BY c.id, c.name, c.image
                ORDER BY c.name COLLATE NOCASE
                """,
                (room,),
            )
            rows = await cur.fetchall()
            await cur.close()
        return [
            {"id": r[0], "name": r[1], "image": r[2] or "", "itemCount": r[3]} for r in rows
        ]

    async def create_cupboard(self, room: str, name: str, image: str) -> int | None:
        async with self._lock:
            conn = self._c()
            cur = await conn.execute("SELECT id FROM rooms WHERE name = ?", (room,))
            row = await cur.fetchone()
            if not row:
                return None
            cur = await conn.execute(
                "INSERT INTO cupboards (name, room_id, image) VALUES (?, ?, ?)",
                (name, row[0], image),
            )
            await conn.commit()
            return cur.lastrowid

    async def update_cupboard(
        self, cupboard_id: int, name: str | None, image: str | None
    ) -> tuple[int, str | None]:
        async with self._lock:
            conn = self._c()
            old_image = None
            if image is not None:
                cur = await conn.execute(
                    "SELECT image FROM cupboards WHERE id = ?", (cupboard_id,)
                )
                row = await cur.fetchone()
                old_image = row[0] if row else None

            updates, params = [], []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if image is not None:
                updates.append("image = ?")
                params.append(image)
            if not updates:
                return 0, None
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(cupboard_id)
            cur = await conn.execute(
                f"UPDATE cupboards SET {', '.join(updates)} WHERE id = ?", params
            )
            await conn.commit()
            stale = old_image if (image is not None and old_image and old_image != image) else None
            return cur.rowcount, stale

    async def delete_cupboard(self, cupboard_id: int) -> tuple[int, list[str]]:
        async with self._lock:
            conn = self._c()
            images: list[str] = []
            cur = await conn.execute(
                "SELECT image FROM cupboards WHERE id = ? AND image IS NOT NULL AND image != ''",
                (cupboard_id,),
            )
            row = await cur.fetchone()
            if row:
                images.append(row[0])
            cur = await conn.execute(
                """
                SELECT i.image FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                WHERE s.cupboard_id = ? AND i.image IS NOT NULL AND i.image != ''
                """,
                (cupboard_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute(
                """
                SELECT o.image FROM organizers o
                JOIN shelves s ON o.shelf_id = s.id
                WHERE s.cupboard_id = ? AND o.image IS NOT NULL AND o.image != ''
                """,
                (cupboard_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute("DELETE FROM cupboards WHERE id = ?", (cupboard_id,))
            await conn.commit()
            return cur.rowcount, images

    # ------------------------------------------------------------------ #
    # Shelves
    # ------------------------------------------------------------------ #

    async def list_shelves(self, room: str, cupboard: str) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT s.id, s.name,
                       COUNT(DISTINCT o.id) AS organizer_count,
                       COUNT(DISTINCT i.id) AS item_count
                FROM shelves s
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                LEFT JOIN organizers o ON s.id = o.shelf_id
                LEFT JOIN items i ON s.id = i.shelf_id
                WHERE r.name = ? AND c.name = ?
                GROUP BY s.id, s.name
                ORDER BY s.name COLLATE NOCASE
                """,
                (room, cupboard),
            )
            rows = await cur.fetchall()
            await cur.close()
        return [
            {"id": r[0], "name": r[1], "organizerCount": r[2], "itemCount": r[3]} for r in rows
        ]

    async def create_shelf(self, room: str, cupboard: str, name: str) -> int | None:
        async with self._lock:
            conn = self._c()
            cur = await conn.execute(
                """
                SELECT c.id FROM cupboards c
                JOIN rooms r ON c.room_id = r.id
                WHERE r.name = ? AND c.name = ?
                """,
                (room, cupboard),
            )
            row = await cur.fetchone()
            if not row:
                return None
            cur = await conn.execute(
                "INSERT INTO shelves (name, cupboard_id) VALUES (?, ?)", (name, row[0])
            )
            await conn.commit()
            return cur.lastrowid

    async def update_shelf(self, shelf_id: int, name: str) -> int:
        async with self._lock:
            cur = await self._c().execute(
                "UPDATE shelves SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, shelf_id),
            )
            await self._c().commit()
            return cur.rowcount

    async def delete_shelf(self, shelf_id: int) -> tuple[int, list[str]]:
        async with self._lock:
            conn = self._c()
            images: list[str] = []
            cur = await conn.execute(
                "SELECT image FROM items WHERE shelf_id = ? AND image IS NOT NULL AND image != ''",
                (shelf_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute(
                "SELECT image FROM organizers WHERE shelf_id = ? AND image IS NOT NULL AND image != ''",
                (shelf_id,),
            )
            images.extend(row[0] for row in await cur.fetchall())
            cur = await conn.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))
            await conn.commit()
            return cur.rowcount, images

    # ------------------------------------------------------------------ #
    # Organizers
    # ------------------------------------------------------------------ #

    async def list_organizers(
        self, room: str, cupboard: str, shelf: str
    ) -> dict[str, Any]:
        async with self._lock:
            conn = self._c()
            cur = await conn.execute(
                """
                SELECT o.id, o.name, o.image, COUNT(DISTINCT i.id) AS item_count
                FROM organizers o
                JOIN shelves s ON o.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                LEFT JOIN items i ON o.id = i.organizer_id
                WHERE r.name = ? AND c.name = ? AND s.name = ?
                GROUP BY o.id, o.name, o.image
                ORDER BY o.name COLLATE NOCASE
                """,
                (room, cupboard, shelf),
            )
            organizers = [
                {"id": r[0], "name": r[1], "image": r[2] or "", "itemCount": r[3]}
                for r in await cur.fetchall()
            ]
            cur = await conn.execute(
                """
                SELECT COUNT(i.id)
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                WHERE r.name = ? AND c.name = ? AND s.name = ? AND i.organizer_id IS NULL
                """,
                (room, cupboard, shelf),
            )
            without = (await cur.fetchone())[0]
            await cur.close()
        return {"organizers": organizers, "itemsWithoutOrganizer": without}

    async def create_organizer(
        self, room: str, cupboard: str, shelf: str, name: str, image: str
    ) -> int | None:
        async with self._lock:
            conn = self._c()
            cur = await conn.cursor()
            shelf_id = await self._resolve_shelf_id(cur, room, cupboard, shelf)
            if shelf_id is None:
                await cur.close()
                return None
            await cur.execute(
                "INSERT INTO organizers (name, image, shelf_id) VALUES (?, ?, ?)",
                (name, image, shelf_id),
            )
            new_id = cur.lastrowid
            await cur.close()
            await conn.commit()
            return new_id

    async def update_organizer(
        self,
        organizer_id: int,
        name: str | None,
        image: str | None,
        move: tuple[str, str, str] | None,
    ) -> tuple[int, str | None, str | None]:
        """Returns (rowcount, stale_image_or_None, error_or_None)."""
        async with self._lock:
            conn = self._c()
            cur = await conn.cursor()
            old_image = None
            if image is not None:
                await cur.execute(
                    "SELECT image FROM organizers WHERE id = ?", (organizer_id,)
                )
                row = await cur.fetchone()
                old_image = row[0] if row else None

            updates, params = [], []
            move_shelf_id = None
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if image is not None:
                updates.append("image = ?")
                params.append(image)

            if move is not None:
                room, cupboard, shelf = move
                move_shelf_id = await self._resolve_shelf_id(cur, room, cupboard, shelf)
                if move_shelf_id is None:
                    await cur.close()
                    return 0, None, "Destination shelf not found"
                updates.append("shelf_id = ?")
                params.append(move_shelf_id)

            if not updates:
                await cur.close()
                return 0, None, None

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(organizer_id)

            # Moving an organizer is two writes (its items follow it to the new
            # shelf, then the organizer itself) — make them atomic.
            async with self._transaction() as tconn:
                if move_shelf_id is not None:
                    await tconn.execute(
                        "UPDATE items SET shelf_id = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE organizer_id = ?",
                        (move_shelf_id, organizer_id),
                    )
                upd = await tconn.execute(
                    f"UPDATE organizers SET {', '.join(updates)} WHERE id = ?", params
                )
                count = upd.rowcount
            await cur.close()
            stale = old_image if (image is not None and old_image and old_image != image) else None
            return count, stale, None

    async def delete_organizer(
        self, organizer_id: int
    ) -> tuple[bool, str | None, list[str], int]:
        """Hard-delete organizer + its items. Returns (deleted, org_image, item_images, items_deleted)."""
        async with self._lock:
            conn = self._c()
            cur = await conn.execute(
                "SELECT image FROM organizers WHERE id = ?", (organizer_id,)
            )
            row = await cur.fetchone()
            org_image = row[0] if row else None
            cur = await conn.execute(
                "SELECT image FROM items WHERE organizer_id = ?", (organizer_id,)
            )
            item_images = [r[0] for r in await cur.fetchall() if r[0]]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM items WHERE organizer_id = ?", (organizer_id,)
            )
            items_count = (await cur.fetchone())[0]
            # Deleting the organizer cascades to its items (FK ON DELETE CASCADE);
            # items_count above is the number that will be removed.
            cur = await conn.execute("DELETE FROM organizers WHERE id = ?", (organizer_id,))
            await conn.commit()
            deleted = cur.rowcount > 0
            return deleted, org_image, item_images, items_count

    # ------------------------------------------------------------------ #
    # Items
    # ------------------------------------------------------------------ #

    @staticmethod
    def _item_row_to_dict(r) -> dict[str, Any]:
        location = f"{r['room']} / {r['cupboard']} / {r['shelf']}"
        if r["organizer"]:
            location += f" / {r['organizer']}"
        return {
            "id": r["id"],
            "name": r["name"],
            "image": r["image"] or "",
            "quantity": r["quantity"],
            "min_quantity": r["min_quantity"],
            "track_quantity": bool(r["track_quantity"]),
            "aliases": r["aliases"],
            "barcode": r["barcode"],
            "room": r["room"],
            "cupboard": r["cupboard"],
            "shelf": r["shelf"],
            "organizer": r["organizer"],
            "location": location,
        }

    async def list_items(
        self, room: str, cupboard: str, shelf: str, organizer: str | None
    ) -> list[dict[str, Any]]:
        async with self._lock:
            conn = self._c()
            if organizer:
                cur = await conn.execute(
                    """
                    SELECT i.id, i.name, i.image, i.quantity, i.min_quantity,
                           i.track_quantity, i.aliases, i.barcode,
                           r.name AS room, c.name AS cupboard, s.name AS shelf,
                           o.name AS organizer
                    FROM items i
                    JOIN organizers o ON i.organizer_id = o.id
                    JOIN shelves s ON i.shelf_id = s.id
                    JOIN cupboards c ON s.cupboard_id = c.id
                    JOIN rooms r ON c.room_id = r.id
                    WHERE r.name = ? AND c.name = ? AND s.name = ? AND o.name = ?
                    ORDER BY i.created_at DESC
                    """,
                    (room, cupboard, shelf, organizer),
                )
            else:
                cur = await conn.execute(
                    """
                    SELECT i.id, i.name, i.image, i.quantity, i.min_quantity,
                           i.track_quantity, i.aliases, i.barcode,
                           r.name AS room, c.name AS cupboard, s.name AS shelf,
                           NULL AS organizer
                    FROM items i
                    JOIN shelves s ON i.shelf_id = s.id
                    JOIN cupboards c ON s.cupboard_id = c.id
                    JOIN rooms r ON c.room_id = r.id
                    WHERE r.name = ? AND c.name = ? AND s.name = ? AND i.organizer_id IS NULL
                    ORDER BY i.created_at DESC
                    """,
                    (room, cupboard, shelf),
                )
            rows = await cur.fetchall()
            await cur.close()
        return [self._item_row_to_dict(r) for r in rows]

    async def list_all_items(self) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT i.id, i.name, i.image, i.quantity, i.min_quantity,
                       i.track_quantity, i.aliases, i.barcode,
                       r.name AS room, c.name AS cupboard, s.name AS shelf,
                       o.name AS organizer
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                LEFT JOIN organizers o ON i.organizer_id = o.id
                ORDER BY i.created_at DESC
                """
            )
            rows = await cur.fetchall()
            await cur.close()
        return [self._item_row_to_dict(r) for r in rows]

    async def find_item_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT i.id, i.name, i.image, i.quantity, i.min_quantity,
                       i.track_quantity, i.aliases, i.barcode,
                       r.name AS room, c.name AS cupboard, s.name AS shelf,
                       o.name AS organizer
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                LEFT JOIN organizers o ON i.organizer_id = o.id
                WHERE i.barcode = ?
                ORDER BY i.created_at DESC
                LIMIT 1
                """,
                (barcode,),
            )
            row = await cur.fetchone()
            await cur.close()
        return self._item_row_to_dict(row) if row else None

    async def create_item(
        self,
        room: str,
        cupboard: str,
        shelf: str,
        organizer: str | None,
        data: dict[str, Any],
    ) -> int | None:
        async with self._lock:
            conn = self._c()
            cur = await conn.cursor()
            shelf_id = await self._resolve_shelf_id(cur, room, cupboard, shelf)
            if shelf_id is None:
                await cur.close()
                return None
            organizer_id = None
            if organizer:
                organizer_id = await self._resolve_organizer_id(
                    cur, room, cupboard, shelf, organizer
                )
            await cur.execute(
                """
                INSERT INTO items
                    (name, aliases, barcode, image, shelf_id, organizer_id,
                     quantity, min_quantity, track_quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data.get("aliases"),
                    data.get("barcode") or None,
                    data.get("image", ""),
                    shelf_id,
                    organizer_id,
                    data.get("quantity"),
                    data.get("min_quantity"),
                    1 if data.get("track_quantity") else 0,
                ),
            )
            new_id = cur.lastrowid
            await cur.close()
            await conn.commit()
            return new_id

    async def update_item(
        self, item_id: int, data: dict[str, Any]
    ) -> tuple[int, str | None, str | None]:
        """Partial update + optional move. Returns (rowcount, stale_image, error)."""
        async with self._lock:
            conn = self._c()
            cur = await conn.cursor()

            new_image = data.get("image")
            old_image = None
            if new_image is not None:
                await cur.execute("SELECT image FROM items WHERE id = ?", (item_id,))
                row = await cur.fetchone()
                old_image = row[0] if row else None

            updates, params = [], []
            if "name" in data and data["name"] is not None:
                updates.append("name = ?")
                params.append(data["name"])
            if "aliases" in data and data["aliases"] is not None:
                updates.append("aliases = ?")
                params.append(data["aliases"])
            if "barcode" in data:
                updates.append("barcode = ?")
                params.append(data["barcode"] or None)
            if new_image is not None:
                updates.append("image = ?")
                params.append(new_image)
            if "quantity" in data:
                updates.append("quantity = ?")
                params.append(data["quantity"])
            if "min_quantity" in data:
                updates.append("min_quantity = ?")
                params.append(data["min_quantity"])
            if data.get("track_quantity") is not None:
                updates.append("track_quantity = ?")
                params.append(1 if data["track_quantity"] else 0)

            move_room = data.get("room")
            move_cupboard = data.get("cupboard")
            move_shelf = data.get("shelf")
            if move_room and move_cupboard and move_shelf:
                shelf_id = await self._resolve_shelf_id(
                    cur, move_room, move_cupboard, move_shelf
                )
                if shelf_id is None:
                    await cur.close()
                    return 0, None, "Destination shelf not found"
                updates.append("shelf_id = ?")
                params.append(shelf_id)
                organizer_id = None
                move_org = data.get("organizer")
                if move_org:
                    organizer_id = await self._resolve_organizer_id(
                        cur, move_room, move_cupboard, move_shelf, move_org
                    )
                    if organizer_id is None:
                        await cur.close()
                        return 0, None, f"Organizer '{move_org}' not found"
                updates.append("organizer_id = ?")
                params.append(organizer_id)

            if not updates:
                await cur.close()
                return 0, None, None

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(item_id)
            await cur.execute(
                f"UPDATE items SET {', '.join(updates)} WHERE id = ?", params
            )
            count = cur.rowcount
            await cur.close()
            await conn.commit()
            stale = (
                old_image
                if (new_image is not None and old_image and old_image != new_image)
                else None
            )
            return count, stale, None

    async def update_item_quantity(
        self,
        item_id: int,
        quantity: Any = _UNSET,
        min_quantity: Any = _UNSET,
        track_quantity: Any = None,
    ) -> int:
        async with self._lock:
            conn = self._c()
            updates, params = [], []
            if quantity is not _UNSET:
                updates.append("quantity = ?")
                params.append(_as_int_or_none(quantity))
            if min_quantity is not _UNSET:
                updates.append("min_quantity = ?")
                params.append(_as_int_or_none(min_quantity))
            if track_quantity is not None:
                updates.append("track_quantity = ?")
                params.append(1 if track_quantity else 0)
            if not updates:
                return 0
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(item_id)
            cur = await conn.execute(
                f"UPDATE items SET {', '.join(updates)} WHERE id = ?", params
            )
            await conn.commit()
            return cur.rowcount

    async def delete_item(self, item_id: int) -> tuple[int, str | None]:
        async with self._lock:
            conn = self._c()
            cur = await conn.execute("SELECT image FROM items WHERE id = ?", (item_id,))
            row = await cur.fetchone()
            old_image = row[0] if row else None
            cur = await conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            await conn.commit()
            return cur.rowcount, old_image

    async def consume_item(self, item_id: int) -> tuple[dict[str, Any] | None, str | None]:
        """Decrement quantity by 1 if tracked + in stock. Returns (result, error)."""
        async with self._lock:
            conn = self._c()
            cur = await conn.execute(
                """
                SELECT i.id, i.name, i.aliases, i.quantity, i.min_quantity, i.track_quantity,
                       r.name AS room, c.name AS cupboard, s.name AS shelf
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                WHERE i.id = ?
                """,
                (item_id,),
            )
            item = await cur.fetchone()
            if not item:
                return None, "Item not found"
            if not item["track_quantity"]:
                return None, "Item does not have quantity tracking enabled"
            if item["quantity"] is None or item["quantity"] <= 0:
                return None, "Item quantity is already 0 or not set"

            new_qty = item["quantity"] - 1
            await conn.execute(
                "UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_qty, item_id),
            )
            await conn.commit()
            location = f"{item['room']} / {item['cupboard']} / {item['shelf']}"
            is_low = item["min_quantity"] is not None and new_qty <= item["min_quantity"]
            return (
                {
                    "id": item["id"],
                    "name": item["name"],
                    "aliases": item["aliases"],
                    "old_quantity": item["quantity"],
                    "new_quantity": new_qty,
                    "min_quantity": item["min_quantity"],
                    "is_low_stock": is_low,
                    "room": item["room"],
                    "cupboard": item["cupboard"],
                    "shelf": item["shelf"],
                    "location": location,
                },
                None,
            )

    async def low_stock_payload(self, item_id: int) -> dict[str, Any] | None:
        """Return the low-stock event payload for an item, or None if not low."""
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT i.id, i.name, i.aliases, i.quantity, i.min_quantity, i.track_quantity,
                       r.name AS room, c.name AS cupboard, s.name AS shelf
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                WHERE i.id = ?
                """,
                (item_id,),
            )
            row = await cur.fetchone()
            await cur.close()
        if not row or not row["track_quantity"]:
            return None
        qty, minq = row["quantity"], row["min_quantity"]
        if qty is None or minq is None or qty > minq:
            return None
        return {
            "item_id": row["id"],
            "name": row["name"],
            "aliases": row["aliases"],
            "quantity": qty,
            "min_quantity": minq,
            "room": row["room"],
            "cupboard": row["cupboard"],
            "shelf": row["shelf"],
            "location": f"{row['room']} / {row['cupboard']} / {row['shelf']}",
        }

    # ------------------------------------------------------------------ #
    # Sensor queries
    # ------------------------------------------------------------------ #

    async def count_items(self) -> int:
        async with self._lock:
            cur = await self._c().execute("SELECT COUNT(*) FROM items")
            return (await cur.fetchone())[0]

    async def low_stock_items(self) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT i.id, i.name, i.quantity, i.min_quantity,
                       r.name AS room, c.name AS cupboard, s.name AS shelf
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                WHERE i.track_quantity = 1
                  AND i.quantity IS NOT NULL
                  AND i.min_quantity IS NOT NULL
                  AND i.quantity <= i.min_quantity
                ORDER BY i.quantity ASC
                """
            )
            rows = await cur.fetchall()
            await cur.close()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "quantity": r["quantity"],
                "min_quantity": r["min_quantity"],
                "room": r["room"],
                "cupboard": r["cupboard"],
                "shelf": r["shelf"],
                "location": f"{r['room']} / {r['cupboard']} / {r['shelf']}",
            }
            for r in rows
        ]

    async def tracked_items(self) -> list[dict[str, Any]]:
        async with self._lock:
            cur = await self._c().execute(
                """
                SELECT i.id, i.name, i.quantity, i.min_quantity,
                       r.name AS room, c.name AS cupboard, s.name AS shelf
                FROM items i
                JOIN shelves s ON i.shelf_id = s.id
                JOIN cupboards c ON s.cupboard_id = c.id
                JOIN rooms r ON c.room_id = r.id
                WHERE i.track_quantity = 1 AND i.min_quantity IS NOT NULL
                ORDER BY i.name COLLATE NOCASE
                """
            )
            rows = await cur.fetchall()
            await cur.close()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "quantity": r["quantity"],
                "min_quantity": r["min_quantity"],
                "room": r["room"],
                "cupboard": r["cupboard"],
                "shelf": r["shelf"],
                "is_low": (
                    r["quantity"] is not None
                    and r["min_quantity"] is not None
                    and r["quantity"] <= r["min_quantity"]
                ),
            }
            for r in rows
        ]
