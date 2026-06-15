"""
M9 数据迁移脚本 - 给老数据补 owner_agent_id

用法：
    python scripts/migrate_add_owner.py           # 真迁移
    python scripts/migrate_add_owner.py --dry-run  # 预览
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


# Windows GBK 终端默认编码不支持 emoji, 这里强制 stdout 用 utf-8
# reconfigure 是 Python 3.7+ 的稳定 API
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


LEGACY_OWNER = "legacy"  # 老数据统一标记


def migrate_file(path: Path, dry_run: bool = False) -> dict:
    """迁移一个 JSON 文件
    返回 {"file": str, "updated": int, "skipped": int, "total": int}
    """
    if not path.exists():
        return {"file": str(path), "updated": 0, "skipped": 0, "total": 0, "missing": True}

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {"file": str(path), "updated": 0, "skipped": 0, "total": 0, "not_list": True}

    updated = 0
    skipped = 0
    for item in raw:
        if not isinstance(item, dict):
            skipped += 1
            continue
        if "owner_agent_id" in item:
            skipped += 1  # 已经有
            continue
        item["owner_agent_id"] = LEGACY_OWNER
        updated += 1

    if not dry_run and updated > 0:
        # 原子写
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    return {
        "file": str(path),
        "updated": updated,
        "skipped": skipped,
        "total": len(raw),
    }


def backup_file(path: Path) -> Path:
    """备份原文件到 path.bak.YYYYMMDD-HHMMSS"""
    if not path.exists():
        return path
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak.{ts}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def main():
    parser = argparse.ArgumentParser(description="M9 数据迁移 - 给老数据补 owner_agent_id")
    parser.add_argument("--data-dir", default="data", help="数据目录 (默认: data)")
    parser.add_argument("--dry-run", action="store_true", help="只预览不真改")
    parser.add_argument("--no-backup", action="store_true", help="不备份")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        sys.exit(1)

    target_files = ["jd.json", "candidates.json", "matches.json", "requests.json"]
    print(f"📁 数据目录: {data_dir}")
    print(f"🔧 模式: {'DRY-RUN (仅预览)' if args.dry_run else '实际迁移'}")
    print(f"📝 目标字段: owner_agent_id = '{LEGACY_OWNER}'")
    print()

    if not args.dry_run and not args.no_backup:
        # 备份现有文件
        for name in target_files:
            p = data_dir / name
            if p.exists():
                bak = backup_file(p)
                print(f"  💾 备份: {p.name} -> {bak.name}")

    print()
    total_updated = 0
    for name in target_files:
        result = migrate_file(data_dir / name, dry_run=args.dry_run)
        if result.get("missing"):
            print(f"  ⏭  {name}: 不存在，跳过")
        elif result.get("not_list"):
            print(f"  ⚠  {name}: 不是 list 格式，跳过")
        else:
            print(f"  📝 {name}: 总 {result['total']} 条，更新 {result['updated']} 条，跳过 {result['skipped']} 条")
            total_updated += result["updated"]

    print()
    if args.dry_run:
        print(f"🔍 预览完成。将更新 {total_updated} 条记录。")
        print("   去掉 --dry-run 参数实际执行。")
    else:
        print(f"✅ 迁移完成: 共更新 {total_updated} 条记录")


if __name__ == "__main__":
    main()
