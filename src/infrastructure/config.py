"""
配置管理模块
负责加载和管理配置信息，支持热更新
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import yaml
import json

class Config:
    """配置管理器"""
    
    def __init__(self):
        # 加载环境变量
        load_dotenv()
        
        # 获取项目根目录
        current_file = Path(__file__).resolve()
        self.project_root = current_file.parents[2]  # src/infrastructure/config.py -> src/infrastructure -> src -> root
        
        # 加载配置文件
        self.config_path = self.project_root / "configs" / "config.yaml"
        self.config = self._load_config()
        
        # 从环境变量加载API密钥
        self.api_keys = self._load_api_keys()
        
        # 更新提供商API密钥
        self._update_provider_api_keys()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load config file: {str(e)}")
    
    def _load_api_keys(self) -> Dict[str, str]:
        """从环境变量加载API密钥"""
        api_keys = {}
        
        # 加载访问密钥
        access_keys_str = os.getenv("ACCESS_API_KEYS", "")
        if access_keys_str:
            try:
                # 尝试解析为JSON
                api_keys = json.loads(access_keys_str)
            except json.JSONDecodeError:
                # 如果不是JSON格式，按逗号分隔
                # 使用密钥作为键和值
                keys = [key.strip() for key in access_keys_str.split(",") if key.strip()]
                api_keys = {key: True for key in keys}
        
        return api_keys
    
    def _update_provider_api_keys(self):
        """从环境变量更新提供商API密钥"""
        for provider in self.config.get("providers", {}):
            env_key = f"{provider.upper()}_API_KEY"
            api_key = os.getenv(env_key)
            if api_key:
                self.config["providers"][provider]["api_key"] = api_key
    
    def reload(self):
        """重新加载配置"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self._update_provider_api_keys()
    
    def validate_api_key(self, api_key: str) -> bool:
        """验证API密钥"""
        return api_key in self.api_keys
    
    def get_provider_config(self, provider: str) -> Optional[Dict[str, Any]]:
        """获取提供商配置"""
        return self.config.get("providers", {}).get(provider)
    
    def get_model_config(self, provider: str, model: str) -> Optional[Dict[str, Any]]:
        """获取模型配置
        Args:
            provider: 提供商名称
            model: 模型名称
        Returns:
            Dict[str, Any]: 模型配置，如果未找到返回 None
        """
        provider_config = self.get_provider_config(provider)
        if not provider_config:
            return None
        return provider_config.get("models", {}).get(model, {})
    
    def get_provider_adapter(self, provider: str) -> Optional[str]:
        """获取提供商的适配器名称
        Args:
            provider: 提供商名称
        Returns:
            str: 适配器名称，如果未找到返回 None
        """
        provider_config = self.get_provider_config(provider)
        if not provider_config:
            return None
        return provider_config.get("adapter")
    
    def is_model_supported(self, provider: str, model: str) -> bool:
        """检查模型是否支持"""
        provider_config = self.get_provider_config(provider)
        if not provider_config:
            return False
        models = provider_config.get("models", {})
        # 现在模型是一个字典，其中包含配置信息
        return model in models.keys()
    
    def get_proxy(self, requires_proxy: bool) -> Optional[str]:
        """获取代理配置"""
        if not requires_proxy:
            return None
        return self.config.get("proxy", {}).get("https")
    
    def get_all_providers(self) -> Dict[str, Any]:
        """获取所有提供商配置"""
        return self.config.get("providers", {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get("logging", {})
    
    @property
    def log_format(self) -> str:
        """获取日志格式"""
        return self.config.get("logging", {}).get("format", "text")
    
    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.config.get("logging", {}).get("level", "info")