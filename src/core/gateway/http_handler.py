"""
HTTP请求处理器
处理REST API请求，包括请求验证、响应格式化等
"""
from typing import Dict, Any, AsyncGenerator, Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from ..router import Router
from infrastructure.logging import logger
import time
import json
import uuid

class HTTPHandler:
    """HTTP请求处理器"""
    
    def __init__(self, router: Router):
        self.router = router
    
    def _get_client_addr(self, request: Request) -> str:
        """获取客户端地址，包含端口号"""
        client = request.client
        if client and client.host:
            return f"{client.host}:{client.port}"
        return None
    
    async def handle_chat_completion(
        self,
        request: Request
    ) -> Union[JSONResponse, StreamingResponse]:
        """
        处理聊天补全请求
        
        Args:
            request: FastAPI请求对象
            
        Returns:
            JSONResponse | StreamingResponse: 处理后的响应
            
        Raises:
            HTTPException: 当请求处理出错时
        """
        request_id = str(uuid.uuid4())
        client_addr = self._get_client_addr(request)
        start_time = time.time()
        
        try:
            # 解析请求
            payload = await request.json()
            model = payload.get("model")
            if not model:
                raise ValueError("Model is required")
                
            api_key = request.headers.get("authorization", "").replace("Bearer ", "")
            if not api_key:
                raise ValueError("API key is required")
                
            stream = payload.get("stream", False)
            
            # 记录请求开始
            logger.log_request_start(
                provider="unknown",  # 在路由后更新
                model=model,
                messages=payload.get("messages", []),
                is_stream=stream,
                request_id=request_id,
                client_addr=client_addr
            )
            
            # 处理流式响应
            if stream:
                return StreamingResponse(
                    self._generate_stream(model, api_key, payload, request_id, client_addr),
                    media_type="text/event-stream"
                )
            
            # 处理普通响应
            response = await self.router.route_request(
                model=model,
                api_key=api_key,
                payload=payload,
                request_id=request_id,
                client_addr=client_addr
            )
            
            # 记录请求完成
            duration = time.time() - start_time
            logger.log_request_complete(
                provider=response.get("provider", "unknown"),
                model=model,
                status_code=200,
                duration=duration,
                input_tokens=response.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=response.get("usage", {}).get("completion_tokens", 0),
                is_stream=False,
                messages=payload.get("messages", []),
                response=response,
                request_id=request_id,
                client_addr=client_addr
            )
            
            return JSONResponse(content=response)
            
        except ValueError as e:
            logger.log_request_error(
                provider="unknown",
                model=model if model else "unknown",
                status_code=400,
                error_message=str(e),
                request_id=request_id,
                client_addr=client_addr
            )
            raise HTTPException(status_code=400, detail=str(e))
            
        except PermissionError as e:
            logger.log_request_error(
                provider="unknown",
                model=model if model else "unknown",
                status_code=401,
                error_message=str(e),
                request_id=request_id,
                client_addr=client_addr
            )
            raise HTTPException(status_code=401, detail=str(e))
            
        except Exception as e:
            logger.log_request_error(
                provider="unknown",
                model=model if model else "unknown",
                status_code=500,
                error_message=str(e),
                request_id=request_id,
                client_addr=client_addr
            )
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
    
    async def _generate_stream(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any],
        request_id: str,
        client_addr: str
    ) -> AsyncGenerator[str, None]:  # type: ignore
        """生成流式响应"""
        start_time = time.time()
        try:
            async for chunk in self.router.route_request_stream(
                model,
                api_key,
                payload,
                request_id=request_id,
                client_addr=client_addr
            ):
                if chunk.strip():
                    logger.log_chunk(
                        chunk=chunk,
                        state="sending",
                        request_id=request_id,
                        provider="unknown",
                        model=model
                    )
                    yield f"{chunk}\n\n"
            yield "data: [DONE]\n\n"
            
            # 记录流式请求完成
            duration = time.time() - start_time
            logger.log_request_complete(
                provider="unknown",  # 由于是流式响应，可能无法获取实际provider
                model=model,
                status_code=200,
                duration=duration,
                input_tokens=0,  # 流式响应可能无法获取准确的token数
                output_tokens=0,
                is_stream=True,
                messages=payload.get("messages", []),
                response="[Stream]",
                request_id=request_id,
                client_addr=client_addr
            )
            
        except Exception as e:
            error_chunk = f"data: {json.dumps({'error': str(e)})}\n\n"
            yield error_chunk
            yield "data: [DONE]\n\n"
            
            logger.log_request_error(
                provider="unknown",
                model=model,
                status_code=500,
                error_message=str(e),
                request_id=request_id,
                client_addr=client_addr
            )
            raise
    
    async def handle_models_list(self) -> JSONResponse:
        """
        处理模型列表请求
        
        Returns:
            JSONResponse: 可用模型列表
        """
        request_id = str(uuid.uuid4())
        try:
            models = await self.router.list_models()
            return JSONResponse(content=models)
            
        except Exception as e:
            logger.log_request_error(
                provider="system",
                model="none",
                status_code=500,
                error_message=f"Error listing models: {str(e)}",
                request_id=request_id
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve models list"
            )