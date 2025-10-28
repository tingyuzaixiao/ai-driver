import logging
import sys
from pathlib import Path


def setup_logging(log_path: str):
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 创建文件处理器
    file_name = Path(log_path) / 'app.log'
    file_handler = logging.FileHandler(file_name, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger