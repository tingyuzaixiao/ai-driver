import logging
import os
import time

logger = logging.getLogger(__name__)

class ProcessUtils:
    @staticmethod
    def is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def wait_for_process(pid: int):
        while ProcessUtils.is_process_alive(pid):
            time.sleep(0.5)