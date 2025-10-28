import json
import logging
import queue
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, APIRouter, Body, Request, HTTPException, status

from server.config import setup_logging
from server.aiServer import AiServer
from server.schema import ServerResponse, StartRequest, StopRequest
from server.trainServer import TrainServer

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
    train_server = request.app.state.train_server
    thread_pool.submit(train_server.start_server, app=request.app, start_request=start_request)
    return {"code": 0}

@router.post("/stop", response_model=ServerResponse)
async def stop_training(stop_request: Annotated[StopRequest, Body()], request: Request):
    if not stop_request:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Stop request is None")
    logger.warning("stop_training request: %s", stop_request.model_dump_json())

    thread_pool = request.app.state.thread_pool
    train_server = request.app.state.train_server
    thread_pool.submit(train_server.stop_server, app=request.app, stop_request=stop_request)
    return {"code": 0}

def init_app_state(app: FastAPI):
    platform_url = "http://localhost:9999/admin/"
    base_dir = "/Users/zhangjiang/test"
    ai_server = AiServer(platform_url=platform_url, base_dir=base_dir)
    app.state.ai_server = ai_server

    thread_pool = ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix="aiserver-")
    app.state.thread_pool = thread_pool

    train_server = TrainServer("test.yml")
    app.state.train_server = train_server

    train_queue = queue.Queue(maxsize=100)
    app.state.train_queue = train_queue

def init_ai_server(app: FastAPI):
    ai_server = app.state.ai_server

    params = {}
    params["batch_size"] = 128
    params["epochs"] = 100
    params_str = json.dumps(params)
    ret = ai_server.register_server(port=app.state.port, description="this is a test", params=params_str)
    if not ret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="register server failed")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(ai_server.heartbeat, 'interval', seconds=5, kwargs={'port': app.state.port})
    scheduler.start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动逻辑
    logger.info("应用开始运行")
    init_app_state(app)
    init_ai_server(app)

    try:
        yield  # 应用在此处进入正常运行期
    finally:
        # 关闭逻辑
        logger.info("应用已关闭")

def init(log_path: str, port: int = 8001):
    setup_logging(log_path)

    app = FastAPI(
        title="ai server",
        description="ai server",
        version="1.0.0",
        lifespan=lifespan
    )
    app.include_router(router)

    app.state.port = port
    return app

if __name__ == "__main__":
    log_path = "/Users/zhangjiang/test"
    port = 8001
    app = init(log_path=log_path, port=port)

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port)