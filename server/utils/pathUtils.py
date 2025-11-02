import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class PathUtils:
    @staticmethod
    def create_directories_for_file(file_path: str):
        path_obj = Path(file_path)
        parent_dir = path_obj.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def create_directories(path: str):
        path_obj = Path(path)
        path_obj.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def cleanup_old_files(directory: str, days=10):
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)

        for root, dirs, files in os.walk(directory, topdown=False):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                if os.path.isfile(file_path):
                    try:
                        file_mtime = os.path.getmtime(file_path)
                        if file_mtime < cutoff_time:
                            os.remove(file_path)
                            logger.warning("已删除过期文件: %s", file_path)
                    except OSError as e:
                        logger.error("删除文件 %s 出错", file_path, exc_info=e)

            try:
                if not os.listdir(root):
                    os.rmdir(root)
                    logger.warning("已删除空目录: %s", root)
            except OSError as e:
                logger.error("删除目录 %s 出错", root, exc_info=e)