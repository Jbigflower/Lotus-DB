import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.setting import settings
from src.db.lance_db import init_lance, close_lance


def parse_columns(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    columns = [c.strip() for c in value.split(",") if c.strip()]
    return columns or None


def serialize_item(item):
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return item


async def list_tables(show_counts: bool) -> None:
    manager = await init_lance()
    tables = await manager.list_tables()
    if not tables:
        print("No tables found")
        return
    if show_counts:
        for name in tables:
            table = await manager.db.open_table(name)
            count = await table.count_rows()
            print(f"{name}\t{count}")
    else:
        for name in tables:
            print(name)


async def show_table(
    table_name: str,
    limit: int,
    where: Optional[str],
    columns: Optional[List[str]],
    show_schema: bool,
    show_count: bool,
    output_json: bool,
) -> None:
    manager = await init_lance()
    table = await manager.db.open_table(table_name)
    if show_schema:
        schema = await table.schema()
        print(schema)
    if show_count:
        count = await table.count_rows()
        print(f"Total rows: {count}")
    query = table.query()
    if where:
        query = query.where(where)
    if columns:
        query = query.select(columns)
    query = query.limit(limit)
    rows = await query.to_list()
    data = [serialize_item(r) for r in rows]
    if not data:
        print("No rows")
        return
    if output_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for item in data:
            print(json.dumps(item, ensure_ascii=False))


async def run_async(args: argparse.Namespace) -> None:
    if args.path:
        settings.database.lancedb_path = args.path
    try:
        if args.table:
            await show_table(
                table_name=args.table,
                limit=args.limit,
                where=args.where,
                columns=parse_columns(args.columns),
                show_schema=args.schema,
                show_count=args.count,
                output_json=args.json,
            )
        else:
            await list_tables(show_counts=args.count)
    finally:
        await close_lance()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LanceDB 数据查阅脚本")
    parser.add_argument("--path", help="覆盖 settings.database.lancedb_path")
    parser.add_argument("--table", help="指定表名进行查询")
    parser.add_argument("--where", help="SQL where 条件")
    parser.add_argument("--columns", help="逗号分隔的列名列表")
    parser.add_argument("--limit", type=int, default=5, help="返回行数")
    parser.add_argument("--schema", action="store_true", help="显示表结构")
    parser.add_argument("--count", action="store_true", help="显示表行数")
    parser.add_argument("--json", action="store_true", help="输出为格式化 JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
