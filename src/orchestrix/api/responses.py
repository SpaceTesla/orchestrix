from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def api_response(
    body: BaseModel,
    status_code: int = 200,
    *,
    headers: dict[str, str] | None = None,
    exclude_none: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=exclude_none),
        headers=headers,
    )
