import json
import logging
import os
import select
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from server.core.taskStatus import TaskStatus
from server.schema import StartRequest, StopRequest
from server.utils.pathUtils import PathUtils
from server.utils.processUtils import ProcessUtils

logger = logging.getLogger(__name__)


class TrainingProcess:
    LOG_FILE_NAME = "application.log"
    ERROR_LOG_FILE_NAME = "error.log"

    def __init__(self, task_id: str, start_request: StartRequest, config_file: str, work_dir: str,
                 dataset_file: str, base_dir: str):
        self.task_id = task_id
        self.start_request = start_request
        self.config_file = config_file
        self.work_dir = work_dir
        self.dataset_file = dataset_file
        self.process = None
        self.pid = None
        self.status = TaskStatus.PENDING.name
        self.start_time = None
        self.end_time = None

        os.makedirs(work_dir, exist_ok=True)
        self._init_log(base_dir, task_id)

    def _init_log(self, base_dir: str, task_id: str):
        common_path = (Path(base_dir) / TrainManager.TRAIN_BUCKET / task_id /
                       TrainManager.TRAIN_CONSOLE_BUCKET)
        PathUtils.create_directories(common_path.as_posix())

        self.log_file = (common_path / TrainingProcess.LOG_FILE_NAME).as_posix()
        self.error_file = (common_path / TrainingProcess.ERROR_LOG_FILE_NAME).as_posix()

        with open(self.log_file, 'w') as f:
            f.write(f"log for task {task_id}\n")
        with open(self.error_file, 'w') as f:
            f.write(f"error log for task {task_id}\n")

class TrainManager:
    ONE_DAY_SECONDS = 60 * 60 * 24
    DOWNLOAD_DATASET_MAX_RETRIES = 300
    TRAIN_BUCKET = "task"
    TRAIN_WORK_BUCKET = "work"
    TRAIN_DATASET_BUCKET = "dataset"
    TRAIN_CONFIG_BUCKET = "config"
    TRAIN_CONSOLE_BUCKET = "console"

    """
        config_file: 配置文件路径
        train_module_path：训练脚本所在的模块的路径，不包含模块名
        train_script：训练脚本在模块中的位置，格式：模块名.脚本名(去掉.py)
        base_dir：driver工作路径
        
        假设：训练脚本为：/home/zhanli/server/main.py
        则：train_module_path: /home/zhanli/server
            train_script: main
    """
    def __init__(self, config_file: str,
                 train_module_path: str,
                 train_script: str,
                 base_dir: str,
                 scheduler: BackgroundScheduler):
        logger.warning("config_file: %s, train_module_path: %s, train_script: %s, base_dir: %s",
                       config_file, train_module_path, train_script, base_dir)
        self._base_dir = base_dir
        self._scheduler = scheduler
        self._state_file = (Path(base_dir) / "driver_state.json").as_posix()

        self._config_file = config_file
        try:
            with open(config_file, 'r', encoding='utf-8') as file:
                self._config_content = file.read()
        except FileNotFoundError:
            logger.error("config file: %s not exist", config_file)
            raise SystemExit(1)
        except json.JSONDecodeError as e:
            logger.error("config file: %s is not json", config_file)
            raise SystemExit(1)

        self._train_module_path = train_module_path
        self._train_script = train_script

        self._lock = threading.Lock()
        self._processes: dict[str, TrainingProcess]
        self._processes = dict()

        self._load_state()
        self._start_clean_thread()

    def _start_clean_thread(self):
        clean_directory = (Path(self._base_dir) / TrainManager.TRAIN_BUCKET).as_posix()
        PathUtils.create_directories(clean_directory)

        self._scheduler.add_job(PathUtils.cleanup_old_files, 'interval',
                                seconds=TrainManager.ONE_DAY_SECONDS,
                                kwargs={'directory': clean_directory})

    @property
    def config_content(self):
        return self._config_content

    def _load_state(self):
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    for task_id, process_data in state.items():
                        process = TrainingProcess(
                            task_id=task_id,
                            start_request=StartRequest.model_validate_json(process_data['start_request']),
                            config_file=process_data['config_file'],
                            work_dir=process_data['work_dir'],
                            dataset_file=process_data['dataset_file'],
                            base_dir=self._base_dir
                        )

                        process.status = process_data['status']
                        process.pid = process_data['pid']
                        if process.status == TaskStatus.RUNNING.name and process.pid:
                            if ProcessUtils.is_process_alive(process.pid):
                                logger.warning("reconnected to running process: %s for task: %s", process.pid, task_id)
                            else:
                                process.status = TaskStatus.STOPPED.name

                        if process.status not in [TaskStatus.PENDING.name, TaskStatus.RUNNING.name]:
                            continue
                        process.start_time = process_data['start_time']
                        process.end_time = process_data['end_time']
                        self._processes[process.task_id] = process

                    if len(state.items()) != len(self._processes):
                        self._save_state()
                logger.warning("loaded %s training tasks from state file", len(self._processes))
            except Exception as e:
                logger.error("failed to load state from %s", self._state_file, exc_info=True)

    def _save_state(self):
        state = {}
        with self._lock:
            for task_id, process in self._processes.items():
                state[task_id] = {
                    'task_id': process.task_id,
                    'start_request': process.start_request.model_dump_json(),
                    'config_file': process.config_file,
                    'work_dir': process.work_dir,
                    'dataset_file': process.dataset_file,
                    'status': process.status,
                    'start_time': process.start_time,
                    'end_time': process.end_time,
                    'pid': process.pid
                }

        try:
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
            logger.warning("state saved to file: %s", self._state_file)
        except Exception as e:
            logger.error("failed to save state to %s", self._state_file, exc_info=True)

    def _get_train_dataset_file_dir(self, task_id: str) -> str:
        return (Path(self._base_dir) / TrainManager.TRAIN_BUCKET / task_id /
                TrainManager.TRAIN_DATASET_BUCKET).as_posix()

    @staticmethod
    def _construct_new_task_id(task_id: int) -> str:
        return f"task_{int(time.time())}_{task_id}_{os.getpid()}"

    def start_server(self, app: FastAPI, start_request: StartRequest):
        new_task_id = TrainManager._construct_new_task_id(start_request.taskId)
        dataset_dir = self._get_train_dataset_file_dir(new_task_id)
        PathUtils.create_directories(dataset_dir)

        ai_server = app.state.ai_server
        dataset_file = ai_server.download_dataset(dataset_id=start_request.datasetId,
                                                  label_id=start_request.labelId,
                                                  dataset_dir=dataset_dir,
                                                  max_retries=TrainManager.DOWNLOAD_DATASET_MAX_RETRIES)
        if not dataset_file:
            logger.error("download dataset failed, stop running: %", start_request.model_dump_json())
            return False
        logger.warning("download dataset finished: %s", dataset_file)

        self._start_training(thread_pool=app.state.thread_pool,
                             start_request=start_request,
                             dataset_file=dataset_file,
                             task_id=new_task_id)
        logger.warning("start training task: %s", new_task_id)
        return True

    def stop_server(self, app: FastAPI, stop_request: StopRequest):
        with self._lock:
            if len(self._processes) == 0:
                logger.warning("can not find training process")
                return False

            stop_task_id = None
            for task_id, process in self._processes.items():
                if process.status == TaskStatus.RUNNING.name:
                    stop_task_id = task_id
                    break

        ret = self._stop_training(task_id=stop_task_id, stop_request=stop_request)
        logger.warning("stop training task: %s", task_id)
        return ret

    def _monitor(self, process: TrainingProcess):
        try:
            with (open(process.log_file, "a", encoding='utf-8') as log_out,
                  open(process.error_file, "a", encoding='utf-8') as log_err):
                timeout = 0.1

                while True:
                    readable, _, _ = select.select(
                        [process.process.stdout, process.process.stderr],
                        [],
                        [],
                        timeout
                    )

                    if process.process.stdout in readable:
                        stdout_line = process.process.stdout.readline()
                        if stdout_line:
                            log_out.write(stdout_line)

                    if process.process.stderr in readable:
                        stderr_line = process.process.stderr.readline()
                        if stderr_line:
                            log_err.write(stderr_line)

                    if process.process.poll() is not None:
                        remaining_stdout = process.process.stdout.read()
                        remaining_stderr = process.process.stderr.read()

                        if remaining_stdout:
                            log_out.write(remaining_stdout)
                            log_out.flush()

                        if remaining_stderr:
                            log_err.write(remaining_stderr)
                            log_err.flush()
                        break

                    time.sleep(0.01)
        except Exception as e:
            logger.error("error monitor for task: %s", process.start_request.taskId, exc_info=True)
        finally:
            with self._lock:
                if process.status != TaskStatus.STOPPED.name:
                    process.status = TaskStatus.COMPLETED.name if process.process.returncode == 0 else TaskStatus.FAILED.name
                process.end_time = time.time()
            logger.warning("training task: %s finished with status: %s",process.start_request.taskId, process.status)
            self._save_state()

    def _get_train_config_file(self, task_id: str) -> str:
        return (Path(self._base_dir) / TrainManager.TRAIN_BUCKET / task_id /
                TrainManager.TRAIN_CONFIG_BUCKET / "config.json").as_posix()

    def _get_train_work_dir(self, task_id: str) -> str:
        return (Path(self._base_dir) / TrainManager.TRAIN_BUCKET / task_id /
                TrainManager.TRAIN_WORK_BUCKET).as_posix()

    def _start_training(self, thread_pool: ThreadPoolExecutor, start_request: StartRequest,
                       dataset_file: str, task_id: str) -> None:
        work_dir = self._get_train_work_dir(task_id)
        PathUtils.create_directories(work_dir)

        config_file = self._get_train_config_file(task_id)
        PathUtils.create_directories_for_file(config_file)
        new_params = json.loads(start_request.params)
        with open(config_file, 'w') as file:
            json.dump(new_params, file, indent=4)

        training_process = TrainingProcess(task_id=task_id,
                                           start_request=start_request,
                                           config_file=config_file,
                                           work_dir=work_dir,
                                           dataset_file=dataset_file,
                                           base_dir=self._base_dir)

        env = os.environ.copy()
        if start_request.gpuCount and start_request.gpuCount > 0:
            env["CUDA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(start_request.gpuCount))
        cmd = [
            sys.executable,
            '-m',
            self._train_script,
            '--work_dir', work_dir,
            '--dataset_file', dataset_file,
            '--config_file', config_file,
            '--experiment_name', start_request.experimentName,
            '--run_name', start_request.runName,
            '--tags', repr(start_request.tags)
        ]
        logger.warning("cmd: %s", cmd)
        logger.warning("cwd: %s", self._train_module_path)
        logger.warning("start subprocess: %s begin", task_id)
        try:
            if sys.platform == "win32":
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self._train_module_path,
                    env=env,
                    text=True,
                    creationflags=subprocess.DETACHED_PROCESS
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self._train_module_path,
                    env=env,
                    text=True,
                    preexec_fn=os.setsid
                )
            logger.warning("start subprocess: %s task_id: %s finished", process.pid, task_id)
            # stdout, stderr = process.communicate()  # 等待进程结束并获取输出
            #
            # # 打印所有输出信息以供诊断
            # print(f"Return code: {process.returncode}")
            # print(f"Standard Output:\n{stdout}")
            # print(f"Standard Error:\n{stderr}")

            training_process.process = process
            training_process.pid = process.pid
            training_process.status = TaskStatus.RUNNING.name
            training_process.start_time = time.time()
            with self._lock:
                self._processes[task_id] = training_process

            thread_pool.submit(self._monitor, process=training_process)

            self._save_state()
        except Exception as e:
            logger.error("failed to start subprocess", exc_info=True)
            raise SystemExit

    def _stop_training(self, task_id: str, stop_request: StopRequest) -> bool:
        pid = None
        with self._lock:
            if task_id not in self._processes:
                logger.warning("task: %s not found", task_id)
                return False
            process = self._processes[task_id]
            if not process.pid:
                logger.warning("task: %s pid not exist", task_id)
            if process.status != TaskStatus.RUNNING.name:
                logger.warning("task: %s is not running (current status: %s)", task_id, process.status)
                return False
            pid = process.pid

        try:
            if stop_request.stopType == 0:
                logger.warning("Sent SIGTERM to subprocess: %s begin", pid)
                os.kill(pid, signal.SIGTERM)
                logger.warning("Sent SIGTERM to subprocess: %s end", pid)
                # ProcessUtils.wait_for_process(process.pid)
            else:
                logger.warning("Sent SIGINT to subprocess: %s begin", pid)
                os.kill(pid, signal.SIGINT)
                logger.warning("Sent SIGINT to subprocess: %s end", pid)
                # ProcessUtils.wait_for_process(process.pid)
        except Exception as e:
            logger.error("failed to stop training task: %s", task_id, exc_info=True)
            return False

        with self._lock:
            process = self._processes[task_id]
            if process:
                process.status = TaskStatus.STOPPED.name
            # process.end_time = time.time()
        # self._save_state()
        return True

    @staticmethod
    def test_start_train(config_file: str,
                         train_module_path: str,
                         train_script: str,
                         base_dir: str,
                         scheduler: BackgroundScheduler):
        train_manager = TrainManager(config_file=config_file,
                                     train_module_path=train_module_path,
                                     train_script=train_script,
                                     base_dir=base_dir,
                                     scheduler=scheduler)
        thread_pool = ThreadPoolExecutor(
            max_workers=8,
            thread_name_prefix="driver-")
        start_request = TrainManager._construct_start_request(config_file)
        new_task_id = TrainManager._construct_new_task_id(start_request.taskId)

        train_manager._start_training(thread_pool=thread_pool,
                                      start_request=start_request,
                                      dataset_file="/Users/zhangjiang/PyCharmMiscProject",
                                      task_id=new_task_id)
        logger.warning("test_start_train finished")
        while True:
            time.sleep(1)

    @staticmethod
    def _construct_start_request(config_file: str) -> StartRequest:
        task_id = 1
        run_name = "mmengine-test4"
        experiment_name = "test-zj-3"
        dataset_id = 11
        label_id = 111
        tags = {'description': 'just test'}

        with open(config_file, 'r', encoding='utf-8') as file:
            config_content_dict = json.load(file)
        config_content_dict["train_cfg"]["max_epochs"] = 300
        params = json.dumps(config_content_dict)
        return StartRequest(taskId=task_id, runName=run_name, experimentName=experiment_name,
                            datasetId=dataset_id, labelId=label_id, tags=tags, params=params,
                            gpuCount=None)

        # return StartRequest(taskId=task_id, runName=run_name, experimentName=experiment_name,
        #                     datasetId=dataset_id, labelId=label_id, tags=tags, params=params,
        #                     gpuCount=None)

    @staticmethod
    def test_stop_train(config_file: str,
                        train_module_path: str,
                        train_script: str,
                        base_dir: str,
                        scheduler: BackgroundScheduler):
        train_manager = TrainManager(config_file=config_file,
                                     train_module_path=train_module_path,
                                     train_script=train_script,
                                     base_dir=base_dir,
                                     scheduler=scheduler)
        if len(train_manager._processes) == 0:
            logger.warning("can not find training process")
            return

        stop_request = TrainManager._construct_stop_request()
        for task_id, process in train_manager._processes.items():
            if process.status == TaskStatus.RUNNING.name:
                ret = train_manager._stop_training(task_id=task_id, stop_request=stop_request)
                logger.warning("stop training task: %s ret: %s", task_id, ret)
        logger.warning("test_stop_train finished")


    @staticmethod
    def _construct_stop_request() -> StopRequest:
        return StopRequest(stopType=1)