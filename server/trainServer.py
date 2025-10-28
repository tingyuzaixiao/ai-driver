import logging
import time

from fastapi import FastAPI

from server.schema import StartRequest, TrainCommand, StopRequest

logger = logging.getLogger(__name__)

class TrainServer:
    DOWNLOAD_DATASET_MAX_RETRIES = 300

    def __init__(self, config_file: str):
        logger.warning("config_file: %s", config_file)
        self._config_file = config_file
        # todo

    def start_server(self, app: FastAPI, start_request: StartRequest):
        ai_server = app.state.ai_server
        ret = ai_server.download_dataset(start_request.datasetId, start_request.taskId,
                                         TrainServer.DOWNLOAD_DATASET_MAX_RETRIES)
        if not ret:
            logger.error("download dataset failed, stop running: %", start_request.model_dump_json())
            return False
        file_path = ret
        logger.warning("download dataset finished: %s", file_path)

        train_queue = app.state.train_queue
        train_queue.queue.clear()
        # todo 启动训练
        # 下面仅仅是模拟
        logger.warning("train server running")
        while True:
            if not train_queue.empty():
                train_command = train_queue.get()
                if train_command.command == TrainCommand.STOP_COMMAND:
                    # todo: 终止训练
                    logger.warning("train server stopped")
                    break
            time.sleep(1)
        return True

    def stop_server(self, app: FastAPI, stop_request: StopRequest):
        train_queue = app.state.train_queue
        train_command = TrainCommand(command=TrainCommand.STOP_COMMAND, data=stop_request)
        train_queue.put(train_command)
        return True