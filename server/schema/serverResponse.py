from typing import Annotated

from pydantic import BaseModel, Field


class ServerResponse(BaseModel):
    code: Annotated[int, Field(alias="code", ge=0, description="0: 成功 1: 失败")]
    msg: Annotated[str, Field(None, alias="msg", description="错误原因")]
    data: Annotated[str, Field(None, alias="data", description="补充信息")]