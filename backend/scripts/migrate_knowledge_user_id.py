import sys
from pathlib import Path

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import engine


def _column_exists(table_name: str, column_name: str) -> bool:
    sql = text(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
        """
    )
    with engine.connect() as conn:
        return conn.execute(sql, {"table_name": table_name, "column_name": column_name}).scalar_one() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    sql = text(
        """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND index_name = :index_name
        """
    )
    with engine.connect() as conn:
        return conn.execute(sql, {"table_name": table_name, "index_name": index_name}).scalar_one() > 0


def main() -> None:
    with engine.begin() as conn:
        if not _column_exists("knowledge_documents", "user_id"):
            conn.execute(text("ALTER TABLE knowledge_documents ADD COLUMN user_id BIGINT NULL AFTER id"))
            conn.execute(text("UPDATE knowledge_documents SET user_id = 1 WHERE user_id IS NULL"))
            conn.execute(text("ALTER TABLE knowledge_documents MODIFY COLUMN user_id BIGINT NOT NULL"))

        if not _index_exists("knowledge_documents", "idx_knowledge_documents_user_id"):
            conn.execute(
                text("CREATE INDEX idx_knowledge_documents_user_id ON knowledge_documents(user_id)")
            )

    print("knowledge_documents.user_id 迁移完成。")


if __name__ == "__main__":
    main()
