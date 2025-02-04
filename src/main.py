from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from api.router import Router
from core.logger import logger
from config.config import PROVIDER_MODELS
import time
import json

app = FastAPI()
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1219)