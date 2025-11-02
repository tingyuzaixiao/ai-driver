import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
import apscheduler.executors.pool
from fastapi import FastAPI, APIRouter, Body, Request, HTTPException, status

from server.config import setup_logging
from server.aiServer import AiServer
from server.schema import ServerResponse, StartRequest, StopRequest
from server.trainManager import TrainManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["inner server"]     # 标签，用于API文档分组
)

@router.post("/start", response_model=ServerResponse)
async def start_training(start_request: Annotated[StartRequest, Body()], request: Request):
    if not start_request:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Start request is None")
    logger.warning("start_training request: %s", start_request.model_dump_json())

    thread_pool = request.app.state.thread_pool
    train_manager = request.app.state.train_manager
    thread_pool.submit(train_manager.start_server, app=request.app, start_request=start_request)
    return {"code": 0}

@router.post("/stop", response_model=ServerResponse)
async def stop_training(stop_request: Annotated[StopRequest, Body()], request: Request):
    if not stop_request:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Stop request is None")
    logger.warning("stop_training request: %s", stop_request.model_dump_json())

    thread_pool = request.app.state.thread_pool
    train_manager = request.app.state.train_manager
    thread_pool.submit(train_manager.stop_server, app=request.app, stop_request=stop_request)
    return {"code": 0}

def init_app_state(app: FastAPI, base_dir: str, platform_url: str,
                   config_file: str, train_module_path: str, train_script: str,
                   port: int) -> None:
    app.state.port = port

    ai_server = AiServer(platform_url=platform_url)
    app.state.ai_server = ai_server

    thread_pool = ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix="driver-")
    app.state.thread_pool = thread_pool

    scheduler = BackgroundScheduler(executors={
        'default': apscheduler.executors.pool.ThreadPoolExecutor(8)})
    scheduler.start()
    app.state.scheduler = scheduler

    train_manager = TrainManager(config_file=config_file,
                                 train_module_path=train_module_path,
                                 train_script=train_script,
                                 base_dir=base_dir,
                                 scheduler=scheduler)
    app.state.train_manager = train_manager

def init_ai_server(app: FastAPI, description: str, register_max_retries: int) -> None:
    train_manager = app.state.train_manager

    ai_server = app.state.ai_server
    ret = ai_server.register_server(port=app.state.port,
                                    description=description,
                                    params=train_manager.config_content,
                                    max_retries=register_max_retries)
    if not ret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="register server failed")
    # scheduler = AsyncIOScheduler()
    # scheduler.add_job(ai_server.heartbeat, 'interval', seconds=5, kwargs={'port': app.state.port})
    # scheduler.start()
    scheduler = app.state.scheduler
    scheduler.add_job(ai_server.heartbeat, 'interval', seconds=5,
                      kwargs={'port': app.state.port})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动逻辑
    logger.info("应用开始运行")
    try:
        yield  # 应用在此处进入正常运行期
    finally:
        # 关闭逻辑
        logger.info("应用已关闭")

def init(base_dir: str, platform_url: str, config_file: str,train_module_path: str,
         train_script: str, description: str, port: int, register_max_retries: int=30) -> FastAPI:
    setup_logging(base_dir)

    app = FastAPI(
        title="ai server",
        description="ai server",
        version="1.0.0",
        lifespan=lifespan
    )
    app.include_router(router)

    init_app_state(app=app, base_dir=base_dir, platform_url=platform_url,
                   config_file=config_file, train_module_path=train_module_path,
                   train_script=train_script, port=port)
    init_ai_server(app, description, register_max_retries)
    return app