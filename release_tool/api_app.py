"""FastAPI 应用共享入口。

本模块只负责创建全局 app、注册通用异常处理、挂载前端静态文件和提供 main 入口。
具体业务接口由 app_factory 统一注册到独立 *_api 模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .redmine_api import RedmineError

async def redmine_error_handler(_request: Request, exc: RedmineError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _mount_frontend(app: FastAPI) -> None:
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    index_file = dist / "index.html"
    if not index_file.exists():

        @app.get("/")
        def frontend_missing() -> Dict[str, str]:
            return {"message": "Vue 前端尚未构建。开发时请运行：cd frontend && npm run dev；发布时请先运行 npm run build。"}

        return

    @app.get("/")
    def frontend_index() -> FileResponse:
        return FileResponse(index_file)

    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


def create_base_app() -> FastAPI:
    app = FastAPI(title="Redmine Firmware Release API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(RedmineError, redmine_error_handler)
    _mount_frontend(app)
    return app


app = create_base_app()


def main() -> None:
    from .app_factory import main as run_server

    run_server()


if __name__ == "__main__":
    main()
