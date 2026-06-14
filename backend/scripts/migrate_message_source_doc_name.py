import sys
from pathlib import Path

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import engine


def main() -> None:
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'message_sources'
                  AND column_name = 'doc_name'
                """
            )
        ).scalar_one()
        if not exists:
            conn.execute(text("ALTER TABLE message_sources ADD COLUMN doc_name VARCHAR(255) NULL AFTER score"))
    print("message_sources.doc_name 迁移完成。")


if __name__ == "__main__":
    main()
