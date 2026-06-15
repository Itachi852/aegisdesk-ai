import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.logger import setup_logging
from app.services.bootstrap_service import bootstrap_project


def main() -> None:
    """
    手动执行项目初始化。

    :return: None。
    """
    setup_logging()
    bootstrap_project()


if __name__ == "__main__":
    main()
