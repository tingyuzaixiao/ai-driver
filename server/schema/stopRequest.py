from typing import Annotated

from pydantic import BaseModel, Field


class StopRequest(BaseModel):
    stopType: Annotated[int, Field(alias="stopType", ge=0, description="停止类型")]