"""
LLM Bridge 服务主入口
提供 HTTP 和 WebSocket API 接口
"""
from fastapi import FastAPI, Request, WebSocket
from core.router import Router
from core.gateway.http_handler import HTTPHandler
from core.gateway.websocket_handler import WebSocketHandler
from infrastructure.logging import logger
import uuid

app = FastAPI(
    title="LLM Bridge",
    description="大模型 API 转发服务",
    version="1.0.0"
)

# 初始化组件
router = Router()
http_handler = HTTPHandler(router)
ws_handler = WebSocketHandler(router)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """处理聊天补全请求"""
    return await http_handler.handle_chat_completion(request)

@app.get("/v1/models")
async def list_models():
    """获取可用模型列表"""
    return await http_handler.handle_models_list()

@app.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """处理 WebSocket 连接"""
    client_id = str(uuid.uuid4())
    await ws_handler.connect(websocket, client_id)
    try:
        await ws_handler.handle_message(websocket, client_id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        ws_handler.disconnect(client_id)

@app.on_event("startup")
async def startup_event():
    """服务启动时的初始化"""
    logger.logger.info("LLM Bridge service starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时的清理"""
    logger.logger.info("LLM Bridge service shutting down...")
    await router.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=1219,
        log_level="info"
    )