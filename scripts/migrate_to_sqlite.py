"""
数据迁移脚本：将 JSON 数据迁移到 SQLite
用法: python migrate_to_sqlite.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv()

DATA_DIR = os.getenv("DATA_DIR", "data")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/mediator.db")


def get_json_data(filename: str) -> list:
    """从 JSON 文件读取数据"""
    path = Path(DATA_DIR) / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def create_tables(conn: sqlite3.Connection):
    """创建 SQLite 表结构"""
    cursor = conn.cursor()

    # migrations 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
    """)

    # requests 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            intent TEXT NOT NULL,
            payload TEXT NOT NULL,
            metadata TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # approvals 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            rule_id TEXT,
            decided_by TEXT NOT NULL,
            decision TEXT NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT NOT NULL
        )
    """)

    # routes 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            from_skill TEXT NOT NULL,
            to_skill TEXT NOT NULL,
            forwarded_payload TEXT NOT NULL,
            status TEXT NOT NULL,
            reply_payload TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # quotas 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotas (
            source TEXT PRIMARY KEY,
            hourly_limit INTEGER NOT NULL,
            current_count INTEGER DEFAULT 0,
            window_start TEXT NOT NULL
        )
    """)

    # webhooks 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id TEXT PRIMARY KEY,
            event TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()


def migrate_requests(conn: sqlite3.Connection):
    """迁移 requests 数据"""
    requests = get_json_data("requests.json")
    if not requests:
        print("  [migrate] No requests data to migrate")
        return

    cursor = conn.cursor()
    for req in requests:
        cursor.execute("""
            INSERT OR REPLACE INTO requests (id, source, target, intent, payload, metadata, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req["id"],
            req["source"],
            req["target"],
            req["intent"],
            json.dumps(req["payload"]),
            json.dumps(req.get("metadata", {})),
            req["status"],
            req["created_at"]
        ))
    conn.commit()
    print(f"  [migrate] Migrated {len(requests)} requests")


def migrate_approvals(conn: sqlite3.Connection):
    """迁移 approvals 数据"""
    approvals = get_json_data("approvals.json")
    if not approvals:
        print("  [migrate] No approvals data to migrate")
        return

    cursor = conn.cursor()
    for apr in approvals:
        cursor.execute("""
            INSERT OR REPLACE INTO approvals (id, request_id, rule_id, decided_by, decision, comment, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            apr["id"],
            apr["request_id"],
            apr.get("rule_id"),
            apr["decided_by"],
            apr["decision"],
            apr.get("comment", ""),
            apr["created_at"],
            apr["decided_at"]
        ))
    conn.commit()
    print(f"  [migrate] Migrated {len(approvals)} approvals")


def migrate_routes(conn: sqlite3.Connection):
    """迁移 routes 数据"""
    routes = get_json_data("routes.json")
    if not routes:
        print("  [migrate] No routes data to migrate")
        return

    cursor = conn.cursor()
    for route in routes:
        cursor.execute("""
            INSERT OR REPLACE INTO routes (id, request_id, from_skill, to_skill, forwarded_payload, status, reply_payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            route["id"],
            route["request_id"],
            route["from_skill"],
            route["to_skill"],
            json.dumps(route["forwarded_payload"]),
            route["status"],
            json.dumps(route.get("reply_payload")) if route.get("reply_payload") else None,
            route["created_at"],
            route["updated_at"]
        ))
    conn.commit()
    print(f"  [migrate] Migrated {len(routes)} routes")


def migrate_quotas(conn: sqlite3.Connection):
    """迁移 quotas 数据"""
    quotas = get_json_data("quotas.json")
    if not quotas:
        print("  [migrate] No quotas data to migrate")
        return

    cursor = conn.cursor()
    for quota in quotas:
        cursor.execute("""
            INSERT OR REPLACE INTO quotas (source, hourly_limit, current_count, window_start)
            VALUES (?, ?, ?, ?)
        """, (
            quota["source"],
            quota["hourly_limit"],
            quota["current_count"],
            quota["window_start"]
        ))
    conn.commit()
    print(f"  [migrate] Migrated {len(quotas)} quotas")


def migrate_webhooks(conn: sqlite3.Connection):
    """迁移 webhooks 数据"""
    webhooks = get_json_data("webhooks.json")
    if not webhooks:
        print("  [migrate] No webhooks data to migrate")
        return

    cursor = conn.cursor()
    for wh in webhooks:
        cursor.execute("""
            INSERT OR REPLACE INTO webhooks (id, event, url, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            wh["id"],
            wh["event"],
            wh["url"],
            wh["created_at"]
        ))
    conn.commit()
    print(f"  [migrate] Migrated {len(webhooks)} webhooks")


def main():
    print("\n" + "=" * 50)
    print("数据迁移：JSON -> SQLite")
    print("=" * 50)

    # 确保 data 目录存在
    db_dir = os.path.dirname(SQLITE_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # 连接 SQLite
    conn = sqlite3.connect(SQLITE_DB_PATH)

    try:
        # 创建表
        print("\n[1/6] 创建数据库表...")
        create_tables(conn)

        # 迁移各数据
        print("\n[2/6] 迁移 requests...")
        migrate_requests(conn)

        print("\n[3/6] 迁移 approvals...")
        migrate_approvals(conn)

        print("\n[4/6] 迁移 routes...")
        migrate_routes(conn)

        print("\n[5/6] 迁移 quotas...")
        migrate_quotas(conn)

        print("\n[6/6] 迁移 webhooks...")
        migrate_webhooks(conn)

        # 记录迁移版本
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO migrations (version, applied_at)
            VALUES (?, datetime('now'))
        """, ("v1",))
        conn.commit()

        print("\n" + "=" * 50)
        print("迁移完成！")
        print("=" * 50)

    finally:
        conn.close()


if __name__ == "__main__":
    main()