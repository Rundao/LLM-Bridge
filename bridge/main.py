import sys
sys.path.append(".")
import argparse
import os
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from bridge.api.router import Router
from bridge.api.admin import config_manager, ProviderConfig
from bridge.core.logger import logger
from bridge.config.config import PROVIDER_MODELS
import time
import json
import uvicorn

# 获取项目根目录
current_file = Path(__file__).resolve()
project_root = current_file.parents[1]

app = FastAPI(
    title="LLM Bridge",
    description="A bridge service for LLM API proxying",
    version="1.0.0",
    # 禁用默认的文档页面
    docs_url=None,
    redoc_url=None
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# 添加OPTIONS请求处理
@app.options("/{path:path}")
async def options_handler(request: Request, path: str):
    return JSONResponse(
        status_code=200,
        content={"message": "OK"}
    )

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(project_root / "bridge" / "web" / "static")), name="static")

# 设置模板目录
templates = Jinja2Templates(directory=str(project_root / "bridge" / "web" / "templates"))

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/docs")
async def docs(request: Request):
    return templates.TemplateResponse("docs.html", {"request": request})

@app.get("/playground")
async def playground(request: Request):
    return templates.TemplateResponse("playground.html", {"request": request})

@app.get("/admin")
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# 配置管理API
@app.get("/api/config")
async def get_config():
    return config_manager.load_config()

@app.post("/api/providers/{name}")
async def add_provider(name: str, provider: ProviderConfig):
    try:
        config_manager.add_provider(name, provider)
        return JSONResponse(status_code=201, content={"message": "Provider added successfully"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/providers/{name}")
async def update_provider(name: str, provider: ProviderConfig):
    try:
        config_manager.update_provider(name, provider)
        return {"message": "Provider updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/providers/{name}")
async def delete_provider(name: str):
    try:
        config_manager.delete_provider(name)
        return {"message": "Provider deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

router = Router()

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        # 解析请求
        payload = await request.json()
        model = payload.get("model")
        api_key = request.headers.get("authorization", "").replace("Bearer ", "")
        stream = payload.get("stream", False)

        # 记录开始时间
        start_time = time.time()

        # 处理流式响应
        if stream:
            async def generate():
                try:
                    async for chunk in router.route_request_stream(model, api_key, payload):
                        if chunk.strip():
                            # 确保chunk是正确的SSE格式
                            if not chunk.startswith('data: '):
                                chunk = f"data: {chunk}"
                            yield f"{chunk}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    # 确保错误也以SSE格式返回
                    error_chunk = f"data: {json.dumps({'error': str(e)})}\n\n"
                    yield error_chunk
                    yield "data: [DONE]\n\n"
                    raise
            
            return StreamingResponse(generate(), media_type="text/event-stream")

        # 处理普通响应
        return await router.route_request(model, api_key, payload)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, 
                            detail=f"Internal server error: {str(e)}")
    
@app.get("/v1/models")
async def list_models():
    try:
        models_list = []
        current_time = int(time.time())
        
        # 遍历所有provider和其模型
        for provider, models in PROVIDER_MODELS.items():
            for model in models:
                model_id = f"{provider}/{model}"  # 组合模型ID
                model_obj = {
                    "id": model_id,
                    "object": "model",
                    "created": current_time,
                    "owned_by": provider
                }
                models_list.append(model_obj)
        
        # 返回符合OpenAI规范的响应格式
        return {
            "object": "list",
            "data": models_list
        }
        
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.on_event("shutdown")
async def shutdown_event():
    await router.close()

def main():
    parser = argparse.ArgumentParser(description="Bridge 服务")
    parser.add_argument("-f", "--config", required=True, help="配置文件路径")
    parser.add_argument("--host", default="localhost", help="服务监听地址 (默认: localhost)")
    parser.add_argument("-p", "--port", type=int, default=1219, help="服务监听端口 (默认: 1219)")
    args = parser.parse_args()
    
    # 在这里加载配置并启动代理转发服务
    print(f"配置文件为：{args.config}")
    print(f"启动服务于 {args.host}:{args.port}")
    
    # 启动FastAPI服务器
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
