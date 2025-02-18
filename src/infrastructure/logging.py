"""
日志模块
提供结构化日志记录功能，支持JSON格式输出
"""
import logging
from logging.handlers import RotatingFileHandler
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, Union, Set

from .config import Config

class JsonFormatter(logging.Formatter):
    """JSON格式的日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage()
        }
        return json.dumps(log_data, ensure_ascii=False)

class StructuredLogger:
    """结构化日志记录器"""
    
    # 字段组到具体字段的映射
    FIELD_GROUPS = {
        "basic": {"timestamp", "request_id"},
        "call": {"provider", "model", "client_addr"},
        "metrics": {"duration", "latency", "input_tokens", "output_tokens"},
        "request": {"messages", "parameters", "is_stream"},
        "response": {"response", "chunk"},
        "error": {"status_code", "error", "error_type"}
    }
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger("LLM_Bridge")
        self._setup_logger()
        # 初始化可用字段集合
        self._init_enabled_fields()
    
    def _init_enabled_fields(self):
        """初始化启用的字段集合"""
        self.enabled_fields = set()
        field_groups = self.config.get_logging_config().get("field_groups", {})
        
        # 遍历所有字段组
        for group_name, group_fields in self.FIELD_GROUPS.items():
            # 如果字段组被启用，将其所有字段添加到启用字段集合中
            if field_groups.get(group_name, {}).get("enabled", False):
                self.enabled_fields.update(group_fields)
    
    def _setup_logger(self):
        """配置日志记录器"""
        # 设置日志级别
        log_level = getattr(logging, self.config.log_level.upper())
        self.logger.setLevel(log_level)
        
        # 清除现有的处理器
        self.logger.handlers.clear()
        
        # 获取日志配置
        log_config = self.config.get_logging_config()
        
        # 配置文件输出
        if "output" in log_config and "file" in log_config["output"]:
            file_config = log_config["output"]["file"]
            log_dir = os.path.dirname(file_config["path"])
            
            # 创建日志目录
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # 配置文件处理器
            file_handler = RotatingFileHandler(
                file_config["path"],
                maxBytes=file_config["max_size"],
                backupCount=file_config["backup_count"],
                encoding='utf-8'
            )
            file_handler.setFormatter(self._get_formatter())
            self.logger.addHandler(file_handler)
        
        # 配置控制台输出
        if log_config.get("output", {}).get("console", True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self._get_formatter())
            self.logger.addHandler(console_handler)
    
    def _get_formatter(self) -> logging.Formatter:
        """获取日志格式化器"""
        if self.config.log_format == "json":
            return JsonFormatter()
        else:
            return logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
    
    def _format_log(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化日志数据"""
        # 构建日志数据，只包含启用的字段
        log_data = {
            k: v for k, v in data.items()
            if k in self.enabled_fields and v is not None
        }
        
        # 确保基本事件信息存在
        log_data["event"] = event
        if "timestamp" in self.enabled_fields and "timestamp" not in log_data:
            log_data["timestamp"] = datetime.now().isoformat()
            
        return log_data
    
    def log_request_start(
        self,
        provider: str,
        model: str,
        messages: list,
        is_stream: bool = False,
        input_tokens: Optional[int] = None,
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ):
        """记录请求开始"""
        log_data = self._format_log(
            "request_start",
            {
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "is_stream": is_stream,
                "input_tokens": input_tokens,
                "messages": messages,
                "client_addr": client_addr
            }
        )
        self.logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def log_request_complete(
        self,
        provider: str,
        model: str,
        status_code: int,
        duration: float,
        input_tokens: int,
        output_tokens: int,
        messages: list,
        response: Union[str, Dict[str, Any]],
        is_stream: bool = False,
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ):
        """记录请求完成"""
        log_data = self._format_log(
            "request_complete",
            {
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "status_code": status_code,
                "duration": duration,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "is_stream": is_stream,
                "messages": messages,
                "response": response,
                "client_addr": client_addr
            }
        )
        self.logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def log_request_error(
        self,
        provider: str,
        model: str,
        status_code: int,
        error_message: str,
        messages: Optional[list] = None,
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ):
        """记录请求错误"""
        log_data = self._format_log(
            "request_error",
            {
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "status_code": status_code,
                "error": error_message,
                "messages": messages,
                "client_addr": client_addr
            }
        )
        self.logger.error(json.dumps(log_data, ensure_ascii=False))
    
    def log_chunk(
        self,
        chunk: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        state: str = "received",
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ):
        """记录流式响应的chunk"""
        if self.logger.level > logging.DEBUG:
            return
            
        # 尝试解析chunk中的JSON内容
        try:
            if chunk.startswith('data: '):
                chunk_content = chunk[6:].strip()  # 移除 "data: " 前缀
                if chunk_content != '[DONE]':
                    chunk_data = json.loads(chunk_content)
                    # 保持原始格式的chunk内容
                    chunk = json.dumps(chunk_data, ensure_ascii=False)
        except json.JSONDecodeError:
            pass  # 如果解析失败，保持原始chunk内容
            
        log_data = self._format_log(
            "chunk",
            {
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "chunk": chunk,
                "state": state,
                "client_addr": client_addr
            }
        )
        self.logger.debug(json.dumps(log_data, ensure_ascii=False))
        
    def log_message(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        request_id: Optional[str] = None,
        client_addr: Optional[str] = None
    ):
        """记录消息"""
        log_data = self._format_log(
            "message",
            {
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "message": message,
                "client_addr": client_addr
            }
        )
        self.logger.info(json.dumps(log_data, ensure_ascii=False))

# 创建全局日志实例
logger = StructuredLogger()