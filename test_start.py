import signal
import sys
from pathlib import Path

import apscheduler.executors.pool
from apscheduler.schedulers.background import BackgroundScheduler

from server.config import setup_logging
from server.trainManager import TrainManager

def test_start():
    config_file = "/Users/zhangjiang/PycharmProjects/worker/configs/config.json"
    train_module_path = "/Users/zhangjiang/PycharmProjects/worker"
    train_script = "main"

    current_path = Path.cwd()
    base_dir = current_path.as_posix()
    setup_logging(base_dir)

    scheduler = BackgroundScheduler(executors={'default': apscheduler.executors.pool.ThreadPoolExecutor(8)})
    scheduler.start()
    TrainManager.test_start_train(config_file=config_file, train_module_path=train_module_path,
                                  train_script=train_script, base_dir=base_dir, scheduler=scheduler)

if __name__ == "__main__":
    test_start()