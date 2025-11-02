import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from server.utils.pathUtils import PathUtils


def setup_logging(base_dir, when='D', interval=1, backup_count=7):
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)

    if logger.handlers:
        logger.handlers.clear()

    log_file = (Path(base_dir) / "logs" / "application.log").as_posix()
    PathUtils.create_directories_for_file(log_file)

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding='utf-8'
    )

    file_handler.suffix = "%Y-%m-%d"
    file_handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    formatter = logging.Formatter(
        '%(asctime)s - [ThreadID: %(thread)d] - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)  # 可选
    return logger