"""
路由模块
负责请求的模型选择和转发处理
"""
from typing import Dict, Any, AsyncGenerator, Optional, Tuple
import aiohttp
import time
import json
import asyncio
from datetime import datetime, timedelta
from infrastructure.config import Config
from infrastructure.logging import logger
from adapters.base import ModelAdapter
from adapters.openai import OpenAIAdapter
from adapters.gemini import GeminiAdapter

class Router:
    """请求路由器"""
    
    def __init__(self):
        self.config = Config()
        self.session: Optional[aiohttp.ClientSession] = None
        # 适配器实例缓存，key为 "{provider}:{model}"
        self.adapter_instances: Dict[str, Tuple[ModelAdapter, datetime]] = {}
        # 适配器创建锁
        self.adapter_locks: Dict[str, asyncio.Lock] = {}
        # 实例过期时间（分钟）
        self.instance_ttl = 30
        # 启动清理任务
        asyncio.create_task(self._cleanup_expired_instances())
    
    async def _cleanup_expired_instances(self):
        """定期清理过期的适配器实例"""
        while True:
            try:
                current_time = datetime.now()
                # 找出过期的实例
                expired_keys = [
                    key for key, (_, last_used) in self.adapter_instances.items()
                    if current_time - last_used > timedelta(minutes=self.instance_ttl)
                ]
                
                # 移除过期实例
                for key in expired_keys:
                    del self.adapter_instances[key]
                    if key in self.adapter_locks:
                        del self.adapter_locks[key]
                
                # 每5分钟检查一次
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(60)  # 出错时等待1分钟后重试
    
    async def get_adapter(self, provider: str, model: str) -> ModelAdapter:
        """获取或创建适配器实例"""
        instance_key = f"{provider}:{model}"
        
        # 检查缓存的实例
        if instance_key in self.adapter_instances:
            adapter, _ = self.adapter_instances[instance_key]
            # 更新最后使用时间
            self.adapter_instances[instance_key] = (adapter, datetime.now())
            return adapter
        
        # 获取创建锁
        if instance_key not in self.adapter_locks:
            self.adapter_locks[instance_key] = asyncio.Lock()
        
        async with self.adapter_locks[instance_key]:
            # 二次检查，防止并发创建
            if instance_key in self.adapter_instances:
                adapter, _ = self.adapter_instances[instance_key]
                self.adapter_instances[instance_key] = (adapter, datetime.now())
                return adapter
            
            # 获取适配器类型
            adapter_type = self.config.get_provider_adapter(provider)
            if not adapter_type:
                raise ValueError(f"No adapter type configured for provider: {provider}")
            
            # 创建新实例
            adapter_classes = {
                "openai": OpenAIAdapter,
                "gemini": GeminiAdapter
            }
            
            if adapter_type not in adapter_classes:
                raise ValueError(f"Unknown adapter type: {adapter_type}")
            
            adapter = adapter_classes[adapter_type]()
            self.adapter_instances[instance_key] = (adapter, datetime.now())
            return adapter
    
    async def get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=600,    # 总超时时间 10 分钟
                connect=30,   # 连接超时 30 秒
                sock_read=180 # 读取超时 3 分钟
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    def _parse_model_name(self, model: str) -> Tuple[str, str]:
        """解析模型名称，返回(provider_name, model_name)元组"""
        if "/" in model:
            provider, model_name = model.split("/", 1)
            return provider, model_name
        # 默认使用 closeai
        return "closeai", model
    
    async def _validate_request(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """验证请求参数并返回必要的配置信息"""
        # 验证API密钥
        if not self.config.validate_api_key(api_key):
            logger.log_request_error(
                provider="unknown",
                model=model,
                status_code=401,
                error_message="Invalid API key"
            )
            raise PermissionError("Invalid API key")
        
        # 解析模型名称
        provider, model_name = self._parse_model_name(model)
        
        # 获取提供商配置
        provider_config = self.config.get_provider_config(provider)
        if not provider_config:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Provider not configured: {provider}"
            )
            raise ValueError(f"Provider not configured: {provider}")
        
        # 验证模型是否支持
        if not self.config.is_model_supported(provider, model_name):
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Model not supported: {model_name}"
            )
            raise ValueError(f"Model not supported: {model_name}")
        
        return provider, provider_config
    
    async def route_request(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理普通请求"""
        if payload.get("stream", False):
            raise ValueError("Use route_request_stream for streaming requests")
        
        provider, provider_config = await self._validate_request(model, api_key, payload)
        _, model_name = self._parse_model_name(model)
        
        # 获取适配器实例
        adapter = await self.get_adapter(provider, model_name)
        
        # 准备请求参数
        request_params = {
            "messages": payload.get("messages", []),
            "model": model_name,
            "temperature": payload.get("temperature"),
            "stream": False
        }
        # 添加其他参数，但排除已经设置的
        other_params = {k: v for k, v in payload.items()
                       if k not in request_params}
        request_params.update(other_params)
        
        request_data = await adapter.prepare_request(**request_params)
        
        try:
            session = await self.get_session()
            async with session.post(
                provider_config["base_url"],
                json=request_data,
                headers=adapter.get_headers(provider_config["api_key"]),
                proxy=self.config.get_proxy(provider_config["requires_proxy"])
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"API error: {response.status} - {error_text}")
                
                response_data = await response.json()
                return await adapter.process_response(response_data)
                
        except Exception as e:
            error_response = await adapter.handle_error(e)
            if isinstance(error_response, dict) and "error" in error_response:
                raise RuntimeError(error_response["error"].get("message", str(e)))
            raise RuntimeError(str(e))
    
    async def route_request_stream(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """处理流式请求"""
        provider, provider_config = await self._validate_request(model, api_key, payload)
        _, model_name = self._parse_model_name(model)
        
        # 获取适配器实例
        adapter = await self.get_adapter(provider, model_name)
        
        # 准备请求参数
        request_params = {
            "messages": payload.get("messages", []),
            "model": model_name,
            "temperature": payload.get("temperature"),
            "stream": True
        }
        # 添加其他参数，但排除已经设置的
        other_params = {k: v for k, v in payload.items()
                       if k not in request_params}
        request_params.update(other_params)
        
        request_data = await adapter.prepare_request(**request_params)
        
        try:
            session = await self.get_session()
            async with session.post(
                provider_config["base_url"],
                json=request_data,
                headers=adapter.get_headers(provider_config["api_key"]),
                proxy=self.config.get_proxy(provider_config["requires_proxy"])
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"API error: {response.status} - {error_text}")
                
                async for chunk in adapter.process_stream(response.content):
                    yield chunk
                    
        except Exception as e:
            error_response = await adapter.handle_error(e)
            if isinstance(error_response, dict) and "error" in error_response:
                yield f"data: {json.dumps(error_response)}\n\n"
            else:
                yield f"data: {json.dumps({'error': {'message': str(e)}})}\n\n"
            yield "data: [DONE]\n\n"
            raise RuntimeError(str(e))
    
    async def list_models(self) -> Dict[str, Any]:
        """获取可用模型列表"""
        models_list = []
        current_time = int(time.time())
        
        for provider, config in self.config.get_all_providers().items():
            for model in config.get("models", {}).keys():
                model_id = f"{provider}/{model}"
                model_obj = {
                    "id": model_id,
                    "object": "model",
                    "created": current_time,
                    "owned_by": provider
                }
                models_list.append(model_obj)
        
        return {
            "object": "list",
            "data": models_list
        }
    
    async def close(self):
        """关闭资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None