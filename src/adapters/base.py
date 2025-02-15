"""
模型适配器基类定义
提供统一的接口规范，用于处理不同模型提供商的请求和响应格式转换
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional

class ModelAdapter(ABC):
    """模型适配器基类"""
    
    @abstractmethod
    async def prepare_request(
        self,
        messages: list[Dict[str, str]],
        model: str,
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        准备请求数据
        
        Args:
            messages: 对话消息列表
            model: 模型名称
            temperature: 温度参数
            stream: 是否使用流式响应
            **kwargs: 其他模型特定参数
            
        Returns:
            Dict[str, Any]: 处理后的请求数据
        """
        pass
    
    @abstractmethod
    async def process_response(
        self,
        response: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        处理响应数据
        
        Args:
            response: 原始响应数据
            stream: 是否为流式响应
            
        Returns:
            Dict[str, Any]: 标准化后的响应数据
        """
        pass
    
    @abstractmethod
    async def process_stream(
        self,
        stream_response: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        处理流式响应
        
        Args:
            stream_response: 原始流式响应
            
        Yields:
            str: 处理后的SSE格式数据
        """
        pass
    
    @abstractmethod
    async def handle_error(
        self,
        error: Exception,
        status_code: int = 500
    ) -> Dict[str, Any]:
        """
        处理错误情况
        
        Args:
            error: 异常对象
            status_code: HTTP状态码
            
        Returns:
            Dict[str, Any]: 标准化的错误响应
        """
        pass
    
    def get_headers(self, api_key: str) -> Dict[str, str]:
        """
        获取请求头
        
        Args:
            api_key: API密钥
            
        Returns:
            Dict[str, str]: 请求头字典
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }