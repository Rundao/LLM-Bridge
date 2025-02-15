"""
Gemini API 适配器
处理 Google Gemini API 的请求和响应格式转换
"""
import json
import uuid
from typing import Dict, Any, AsyncGenerator, Optional
from .base import ModelAdapter

class GeminiAdapter(ModelAdapter):
    """Gemini API适配器实现"""
    
    async def prepare_request(
        self,
        messages: list[Dict[str, str]],
        model: str,
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """准备Gemini格式的请求数据"""
        # 转换消息格式
        gemini_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            # Gemini使用"model"代替"assistant"
            if role == "assistant":
                role = "model"
            gemini_messages.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })
        
        request_data = {
            "prompt": {
                "messages": gemini_messages
            },
            "temperature": temperature if temperature is not None else 0.7,
            "maxOutputTokens": kwargs.get("max_tokens", 1024),
            "stopSequences": kwargs.get("stop", []),
            "stream": stream
        }
        
        return request_data
    
    async def process_response(
        self,
        response: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """处理Gemini格式的响应数据"""
        if not isinstance(response, dict):
            raise ValueError("Invalid response format")
            
        # 提取响应内容
        candidates = response.get("candidates", [])
        if not candidates:
            raise ValueError("Empty response from Gemini API")
            
        # 转换为OpenAI格式
        content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        
        return {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "created": response.get("created", 0),
            "model": "gemini",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": candidates[0].get("finishReason", "stop")
            }],
            "usage": response.get("usage", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            })
        }
    
    async def process_stream(
        self,
        stream_response: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """处理Gemini格式的流式响应"""
        async for chunk in stream_response:
            if not chunk:
                continue
                
            try:
                # 解析数据
                data = chunk.decode("utf-8").strip()
                if data == "data: [DONE]":
                    yield data + "\n\n"
                    continue
                    
                if data.startswith("data: "):
                    data = data[6:]
                    
                # 解析JSON数据
                try:
                    chunk_data = json.loads(data)
                    candidates = chunk_data.get("candidates", [])
                    if not candidates:
                        continue
                        
                    # 提取文本内容
                    content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    
                    # 构建OpenAI格式的响应
                    response_data = {
                        "id": str(uuid.uuid4()),
                        "object": "chat.completion.chunk",
                        "created": chunk_data.get("created", 0),
                        "model": "gemini",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": content
                            },
                            "finish_reason": candidates[0].get("finishReason")
                        }]
                    }
                    
                    yield f"data: {json.dumps(response_data)}\n\n"
                    
                except json.JSONDecodeError:
                    continue
                    
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    async def handle_error(
        self,
        error: Exception,
        status_code: int = 500
    ) -> Dict[str, Any]:
        """处理错误情况"""
        error_response = {
            "error": {
                "message": str(error),
                "type": error.__class__.__name__,
                "code": status_code
            }
        }
        
        if hasattr(error, "response") and hasattr(error.response, "text"):
            try:
                error_text = error.response.text
                error_data = json.loads(error_text)
                if isinstance(error_data, dict):
                    if "error" in error_data:
                        error_response["error"].update(error_data["error"])
                    elif "message" in error_data:
                        error_response["error"]["message"] = error_data["message"]
                    else:
                        error_response["error"]["message"] = error_text
            except json.JSONDecodeError:
                error_response["error"]["message"] = error_text
                
        return error_response