"""
OpenAI 格式适配器
处理符合 OpenAI API 格式的请求和响应
"""
import json
import uuid
from typing import Dict, Any, AsyncGenerator, Optional
from .base import ModelAdapter

class OpenAIAdapter(ModelAdapter):
    """OpenAI格式适配器实现"""
    
    async def prepare_request(
        self,
        messages: list[Dict[str, str]],
        model: str,
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """准备OpenAI格式的请求数据"""
        request_data = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if temperature is not None:
            request_data["temperature"] = temperature
            
        # 添加其他可选参数
        for key, value in kwargs.items():
            if value is not None:
                request_data[key] = value
                
        # 从kwargs中获取模型配置
        model_config = kwargs.get('_model_config', {})
        param_config = model_config.get('param_config', {})
        
        if param_config:
            # 1. 更新参数值
            if 'update_params' in param_config:
                for key, value in param_config['update_params'].items():
                    request_data[key] = value

            # 2. 添加新参数
            if 'add_params' in param_config:
                for key, value in param_config['add_params'].items():
                    if key not in request_data:
                        request_data[key] = value

            # 3. 重命名参数
            if 'rename_params' in param_config:
                for old_key, new_key in param_config['rename_params'].items():
                    if old_key in request_data:
                        request_data[new_key] = request_data.pop(old_key)

            # 4. 删除参数
            if 'delete_params' in param_config:
                for key in param_config['delete_params']:
                    request_data.pop(key, None)
                
        return request_data
    
    async def process_response(
        self,
        response: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """处理OpenAI格式的响应数据"""
        if not isinstance(response, dict):
            raise ValueError("Invalid response format")
            
        # 确保响应包含必要的字段
        if "choices" not in response:
            raise ValueError("Response missing choices field")
            
        # 标准化响应格式
        return {
            "id": response.get("id", str(uuid.uuid4())),
            "object": response.get("object", "chat.completion"),
            "created": response.get("created", 0),
            "model": response.get("model", "unknown"),
            "choices": response["choices"],
            "usage": response.get("usage", {})
        }
    
    async def process_stream(
        self,
        stream_response: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """处理OpenAI格式的流式响应"""
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
                    data = data[6:]  # 移除 "data: " 前缀
                    
                # 解析JSON数据
                try:
                    json_data = json.loads(data)
                except json.JSONDecodeError:
                    continue
                    
                # 确保有正确的ID
                if "id" not in json_data:
                    json_data["id"] = str(uuid.uuid4())
                    
                # 构建SSE格式响应
                yield f"data: {json.dumps(json_data)}\n\n"
                
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
                    else:
                        error_response["error"]["message"] = error_text
            except json.JSONDecodeError:
                error_response["error"]["message"] = error_text
                
        return error_response