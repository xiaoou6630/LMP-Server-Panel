import os
import aiosqlite
from contextlib import asynccontextmanager
from backend.config import get_path

DB_PATH = get_path("data", "ml.db")


async def get_db_path():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


@asynccontextmanager
async def get_db():
    db_path = await get_db_path()
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


async def init_db():
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS admin_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS server_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT NOT NULL,
                description TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS modpack (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                identifier TEXT NOT NULL UNIQUE,
                version TEXT DEFAULT '',
                description TEXT DEFAULT '',
                mod_list TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS mod_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_name TEXT NOT NULL UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS server_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_type TEXT NOT NULL DEFAULT 'info',
                message TEXT NOT NULL,
                source TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS network_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network_name TEXT NOT NULL DEFAULT '',
                network_key TEXT NOT NULL DEFAULT '',
                virtual_ip TEXT DEFAULT '',
                ipv4 TEXT DEFAULT '',
                hostname TEXT DEFAULT '',
                proxy_networks TEXT DEFAULT '',
                mapped_listeners TEXT DEFAULT '',
                peers TEXT DEFAULT '',
                external_node TEXT DEFAULT '',
                listeners TEXT DEFAULT '',
                is_connected INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wizard_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step TEXT NOT NULL UNIQUE,
                completed INTEGER DEFAULT 0,
                data TEXT DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM network_config")
        row = await cursor.fetchone()
        if row and row["cnt"] == 0:
            await conn.execute(
                "INSERT INTO network_config (network_name, network_key) VALUES (?, ?)",
                ("", "")
            )

        # Migration: ensure UNIQUE on wizard_state.step for existing DBs
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_wizard_state_step ON wizard_state(step)"
            )
        except Exception:
            pass

        for col in ["peers", "external_node", "listeners", "ipv4", "hostname", "proxy_networks", "mapped_listeners"]:
            try:
                await conn.execute(f"ALTER TABLE network_config ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass

        await conn.commit()


async def get_setting(key: str, default: str = "") -> str:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT config_value FROM server_config WHERE config_key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["config_value"] if row else default


async def set_setting(key: str, value: str, description: str = ""):
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO server_config (config_key, config_value, description)
               VALUES (?, ?, ?)
               ON CONFLICT(config_key) DO UPDATE SET
               config_value=excluded.config_value,
               description=excluded.description,
               updated_at=CURRENT_TIMESTAMP""",
            (key, str(value), description)
        )
        await conn.commit()
