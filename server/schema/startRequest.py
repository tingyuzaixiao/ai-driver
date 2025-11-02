from typing import Annotated, Optional

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    taskId: Annotated[int, Field(alias="taskId", gt=0, description="任务id")]
    runName: Annotated[str, Field(alias="runName", description="run name")]
    experimentName: Annotated[str, Field(alias="experimentName", description="实验名称")]
    params: Annotated[str, Field(alias="params", description="服务参数(json格式)")]
    datasetId: Annotated[int, Field(alias="datasetId", gt=0, description="数据集id")]
    labelId: Annotated[int, Field(alias="labelId", gt=0, description="数据集标注id")]
    tags: Annotated[dict[str, str], Field(alias="tags", description="运行tags")]
    gpuCount: Annotated[Optional[int], Field(default=None, alias="gpuCount", description="gpu数量")]