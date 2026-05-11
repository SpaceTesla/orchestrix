import asyncio
from pathlib import Path

from orchestrix.db.pool import close_pool, init_pool


def _migrations_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "orchestrix"
        / "db"
        / "migrations"
    )


async def main():
    pool = await init_pool()

    try:
        async with pool.acquire() as conn:
            paths = sorted(_migrations_dir().glob("*.sql"))
            if not paths:
                raise FileNotFoundError(f"No .sql files in {_migrations_dir()!s}")
            for path in paths:
                await conn.execute(path.read_text(encoding="utf-8"))
                print(f"Applied {path.name}")
            print("Migrations finished")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
