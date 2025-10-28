from typing import Annotated

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    runName: Annotated[str, Field(alias="experimentName", description="run name")]
    experimentName: Annotated[str, Field(alias="programName", description="实验名称")]
    params: Annotated[str, Field(alias="params", description="服务参数(json格式)")]
    datasetId: Annotated[int, Field(alias="datasetId", gt=0, description="数据集id")]
    taskId: Annotated[int, Field(alias="taskId", gt=0, description="数据集标注id")]
    tags: Annotated[dict[str, str], Field(alias="tags", description="运行tags")]