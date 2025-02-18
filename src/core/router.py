"""
路由模块
负责请求的模型选择和转发处理
"""
from typing import Dict, Any, AsyncGenerator, Optional, Tuple, TypeVar, Callable
import aiohttp
import time
import json
import asyncio
from datetime import datetime, timedelta
from functools import wraps
from infrastructure.config import Config
from infrastructure.logging import logger
from adapters.base import ModelAdapter
from adapters.openai import OpenAIAdapter
from adapters.gemini import GeminiAdapter

# 泛型类型定义
T = TypeVar('T')

class LLMBridgeError(Exception):
    """LLM Bridge 基础异常类"""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

class AuthenticationError(LLMBridgeError):
    """认证错误"""
    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message, status_code=401)

class ValidationError(LLMBridgeError):
    """参数验证错误"""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)

class ProviderError(LLMBridgeError):
    """模型提供商API错误"""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        # 获取错误信息和可能存在的额外信息
        formatted_message = self._format_error_message(message)
        # 将可能的JSON错误存储在details中，而不是直接暴露
        try:
            error_data = json.loads(message)
            if isinstance(error_data, dict):
                details = {**details} if details else {}
                if "error" in error_data:
                    details["provider_error"] = error_data["error"]
        except:
            pass
        
        super().__init__(
            formatted_message,
            status_code=status_code,
            details=details
        )

    def _format_error_message(self, message: str) -> str:
        """格式化错误信息，移除敏感信息和技术细节"""
        return message.strip()

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
        # 每个提供商的请求统计
        self.request_stats: Dict[str, Dict[str, int]] = {}
        # 启动清理任务
        asyncio.create_task(self._cleanup_expired_instances())

    def _log_error(
        self,
        error: Exception,
        provider: str,
        model: str,
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ) -> None:
        """统一的错误日志记录
        
        Args:
            error: 异常对象
            provider: 提供商名称
            model: 模型名称
            request_id: 请求ID
            client_addr: 客户端地址
        """
        if isinstance(error, LLMBridgeError):
            status_code = error.status_code
            # 如果有详细信息，将其添加到错误消息中
            error_message = str(error)
            if error.details:
                error_message = f"{error_message} (Details: {json.dumps(error.details)})"
        else:
            status_code = 500
            error_message = str(error)

        logger.log_request_error(
            provider=provider or "unknown",
            model=model,
            status_code=status_code,
            error_message=error_message,
            request_id=request_id,
            client_addr=client_addr
        )

    def _update_stats(self, provider: str, success: bool) -> None:
        """更新请求统计
        
        Args:
            provider: 提供商名称
            success: 是否成功
        """
        if provider not in self.request_stats:
            self.request_stats[provider] = {"success": 0, "failure": 0}
        
        if success:
            self.request_stats[provider]["success"] += 1
        else:
            self.request_stats[provider]["failure"] += 1
    
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
                logger.log_message(
                    message=f"Error in cleanup task: {str(e)}",
                    provider="system"
                )
                await asyncio.sleep(60)  # 出错时等待1分钟后重试
    
    async def get_adapter(self, provider: str, model: str) -> ModelAdapter:
        """获取或创建适配器实例
        
        Args:
            provider: 提供商名称
            model: 模型名称
            
        Returns:
            ModelAdapter: 适配器实例
            
        Raises:
            ValidationError: 当适配器类型未配置或不存在时
        """
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
                raise ValidationError(f"No adapter type configured for provider: {provider}")
            
            # 创建新实例
            adapter_classes = {
                "openai": OpenAIAdapter,
                "gemini": GeminiAdapter
            }
            
            if adapter_type not in adapter_classes:
                raise ValidationError(f"Unknown adapter type: {adapter_type}")
            
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
        """解析模型名称，返回(provider_name, model_name)元组
        
        Args:
            model: 模型名称，格式为 "provider/model" 或 "model"
                   model 部分可能包含参数标注，如 "model<param>"
                   
        Returns:
            Tuple[str, str]: (provider_name, model_name) 元组
        """
        # 删除模型名称中的参数标注
        def clean_model_name(name: str) -> str:
            if "<" in name and ">" in name:
                # 找到最后一个 < 和第一个 > 之间的内容
                start = name.rfind("<")
                end = name.find(">", start)
                if start != -1 and end != -1:
                    return name[:start] + name[end + 1:]
            return name
            
        if "/" in model:
            provider, model_name = model.split("/", 1)
            return provider, clean_model_name(model_name)
        # 默认使用 closeai
        return "closeai", clean_model_name(model)
    
    async def _validate_request(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any],
        request_id: str = None,
        client_addr: str = None
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """验证请求参数并返回必要的配置信息
        
        Args:
            model: 模型名称
            api_key: API密钥
            payload: 请求参数
            request_id: 请求ID
            client_addr: 客户端地址
        
        Returns:
            Tuple[str, Dict[str, Any], Dict[str, Any]]: 
                (provider_name, provider_config, model_config) 元组
                
        Raises:
            AuthenticationError: 当API密钥无效时
            ValidationError: 当提供商未配置或模型不支持时
        """
        # 验证API密钥
        if not self.config.validate_api_key(api_key):
            logger.log_request_error(
                provider="unknown",
                model=model,
                status_code=401,
                error_message="Invalid API key",
                request_id=request_id,
                client_addr=client_addr
            )
            raise AuthenticationError()
        
        # 解析模型名称
        provider, model_name = self._parse_model_name(model)
        
        # 获取提供商配置
        provider_config = self.config.get_provider_config(provider)
        if not provider_config:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Provider not configured: {provider}",
                request_id=request_id,
                client_addr=client_addr
            )
            raise ValidationError(f"Provider not configured: {provider}")
        
        # 验证模型是否支持
        if not self.config.is_model_supported(provider, model_name):
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Model not supported: {model_name}",
                request_id=request_id,
                client_addr=client_addr
            )
            raise ValidationError(f"Model not supported: {model_name}")
        
        # 获取模型配置
        model_config = self.config.get_model_config(provider, model_name)
        
        return provider, provider_config, model_config
    
    async def route_request(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any],
        request_id: str = None,
        client_addr: str = None
    ) -> Dict[str, Any]:
        """处理普通请求
        
        Args:
            model: 模型名称
            api_key: API密钥
            payload: 请求参数
            request_id: 请求ID
            client_addr: 客户端地址
            
        Returns:
            Dict[str, Any]: API响应结果
            
        Raises:
            ValidationError: 当请求参数无效时
            ProviderError: 当API调用失败时
            LLMBridgeError: 其他错误情况
        """
        if payload.get("stream", False):
            raise ValidationError("Use route_request_stream for streaming requests")
        
        start_time = time.time()
        provider = None
        
        try:
            provider, provider_config, model_config = await self._validate_request(
                model,
                api_key,
                payload,
                request_id,
                client_addr
            )
            _, model_name = self._parse_model_name(model)
            
            # 获取适配器实例
            adapter = await self.get_adapter(provider, model_name)
            
            # 准备请求参数
            request_params = {
                "messages": payload.get("messages", []),
                "model": model_name,
                "temperature": payload.get("temperature"),
                "stream": False,
                "_model_config": model_config  # 传递模型配置
            }
            # 添加其他参数，但排除已经设置的
            other_params = {k: v for k, v in payload.items()
                          if k not in request_params}
            request_params.update(other_params)
            
            request_data = await adapter.prepare_request(**request_params)
            
            session = await self.get_session()
            async with session.post(
                provider_config["base_url"],
                json=request_data,
                headers=adapter.get_headers(provider_config["api_key"]),
                proxy=self.config.get_proxy(provider_config["requires_proxy"]),
                timeout=model_config.get("timeout", 120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    # 返回统一格式的错误信息
                    response_data = f"data: {json.dumps({'error': {'message': error_text, 'type': 'ProviderError', 'code': response.status}})}"
                    return response_data
                
                response_data = await response.json()
                result = await adapter.process_response(response_data)
                
                # 计算并记录耗时
                duration = time.time() - start_time
                logger.log_request_complete(
                    provider=provider,
                    model=model,
                    status_code=response.status,
                    duration=duration,
                    input_tokens=result.get("usage", {}).get("prompt_tokens", 0),
                    output_tokens=result.get("usage", {}).get("completion_tokens", 0),
                    messages=payload.get("messages", []),
                    response=result,
                    is_stream=False,
                    request_id=request_id,
                    client_addr=client_addr
                )
                
                # 更新统计信息
                self._update_stats(provider, True)
                
                return result
                
        except LLMBridgeError as e:
            self._log_error(e, provider, model, request_id, client_addr)
            if provider:
                self._update_stats(provider, False)
            raise
        except Exception as e:
            error = LLMBridgeError(str(e))
            self._log_error(error, provider, model, request_id, client_addr)
            if provider:
                self._update_stats(provider, False)
            raise error
    
    async def route_request_stream(
        self,
        model: str,
        api_key: str,
        payload: Dict[str, Any],
        request_id: str = None,
        client_addr: str = None
    ) -> AsyncGenerator[str, None]:
        """处理流式请求
        
        Args:
            model: 模型名称
            api_key: API密钥
            payload: 请求参数
            request_id: 请求ID
            client_addr: 客户端地址
            
        Yields:
            str: 流式响应的数据块
            
        Raises:
            ValidationError: 当请求参数无效时
            ProviderError: 当API调用失败时
            LLMBridgeError: 其他错误情况
        """
        provider = None
        start_time = time.time()
        try:
            provider, provider_config, model_config = await self._validate_request(
                model,
                api_key,
                payload,
                request_id,
                client_addr
            )
            _, model_name = self._parse_model_name(model)
            
            # 获取适配器实例
            adapter = await self.get_adapter(provider, model_name)
            
            # 准备请求参数
            request_params = {
                "messages": payload.get("messages", []),
                "model": model_name,
                "temperature": payload.get("temperature"),
                "stream": True,
                "_model_config": model_config  # 传递模型配置
            }
            # 添加其他参数，但排除已经设置的
            other_params = {k: v for k, v in payload.items()
                          if k not in request_params}
            request_params.update(other_params)
            
            request_data = await adapter.prepare_request(**request_params)
            
            session = await self.get_session()
            async with session.post(
                provider_config["base_url"],
                json=request_data,
                headers=adapter.get_headers(provider_config["api_key"]),
                proxy=self.config.get_proxy(provider_config["requires_proxy"]),
                timeout=model_config.get("timeout", 120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    duration = time.time() - start_time
                    logger.log_request_complete(
                        provider=provider,
                        model=model,
                        status_code=response.status,
                        duration=duration,
                        input_tokens=0,
                        output_tokens=0,
                        messages=payload.get("messages", []),
                        response=error_text,
                        is_stream=True,
                        request_id=request_id,
                        client_addr=client_addr
                    )
                    # 返回统一格式的错误信息
                    response_data = f"data: {json.dumps({'error': {'message': error_text, 'type': 'ProviderError', 'code': response.status}})}\n\n"
                    yield response_data
                    return
                
                try:
                    async for chunk in adapter.process_stream(response.content):
                        yield chunk
                        
                    # 只有在成功完成流式传输后才记录成功
                    duration = time.time() - start_time
                    logger.log_request_complete(
                        provider=provider,
                        model=model,
                        status_code=200,
                        duration=duration,
                        input_tokens=0,  # 流式响应可能无法获取准确的token数
                        output_tokens=0,
                        messages=payload.get("messages", []),
                        response="[Stream]",
                        is_stream=True,
                        request_id=request_id,
                        client_addr=client_addr
                    )
                except Exception as e:
                    # 如果在流式传输过程中发生错误，确保记录错误状态
                    duration = time.time() - start_time
                    logger.log_request_complete(
                        provider=provider,
                        model=model,
                        status_code=500,
                        duration=duration,
                        input_tokens=0,
                        output_tokens=0,
                        messages=payload.get("messages", []),
                        response=str(e),
                        is_stream=True,
                        request_id=request_id,
                        client_addr=client_addr
                    )
                    raise
                
                # 更新统计信息
                self._update_stats(provider, True)
                    
        except LLMBridgeError as e:
            self._log_error(e, provider, model, request_id, client_addr)
            if provider:
                self._update_stats(provider, False)
            if isinstance(e, ProviderError):
                # 对于服务提供商的错误，直接返回原始错误信息
                yield e.args[0]  # 原始错误文本
            else:
                # 其他系统错误使用标准格式
                yield json.dumps({
                    "error": {
                        "message": str(e),
                        "type": e.__class__.__name__,
                        "code": e.status_code
                    }
                })
        except Exception as e:
            # 将未知异常包装为系统错误
            self._log_error(e, provider, model, request_id, client_addr)
            if provider:
                self._update_stats(provider, False)
            yield json.dumps({
                "error": {
                    "message": "Internal server error",
                    "type": "ServerError",
                    "code": 500
                }
            })
