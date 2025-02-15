"""
日志模块
提供结构化日志记录功能，支持JSON格式输出
"""
import logging
from logging.handlers import RotatingFileHandler
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, Union
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
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger("LLM_Bridge")
        self._setup_logger()
    
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
    
    def _format_log(
        self,
        event: str,
        data: Dict[str, Any],
        include_fields: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """格式化日志数据"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event": event
        }
        
        # 根据配置添加字段
        fields_config = self.config.get_logging_config().get("fields", {})
        if include_fields:
            fields_config.update(include_fields)
        
        for field, enabled in fields_config.items():
            if enabled and field in data:
                log_data[field] = data[field]
        
        return log_data
    
    def log_request_start(
        self,
        provider: str,
        model: str,
        messages: list,
        is_stream: bool = False,
        input_tokens: Optional[int] = None
    ):
        """记录请求开始"""
        log_data = self._format_log(
            "request_start",
            {
                "provider": provider,
                "model": model,
                "is_stream": is_stream,
                "input_tokens": input_tokens,
                "messages": messages
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
        is_stream: bool = False
    ):
        """记录请求完成"""
        log_data = self._format_log(
            "request_complete",
            {
                "provider": provider,
                "model": model,
                "status_code": status_code,
                "duration": duration,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "is_stream": is_stream,
                "messages": messages,
                "response": response
            }
        )
        self.logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def log_request_error(
        self,
        provider: str,
        model: str,
        status_code: int,
        error_message: str,
        messages: Optional[list] = None
    ):
        """记录请求错误"""
        log_data = self._format_log(
            "request_error",
            {
                "provider": provider,
                "model": model,
                "status_code": status_code,
                "error": error_message,
                "messages": messages
            }
        )
        self.logger.error(json.dumps(log_data, ensure_ascii=False))
    
    def log_chunk(
        self,
        chunk: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        state: str = "received"
    ):
        """记录流式响应的chunk"""
        if self.logger.level > logging.DEBUG:
            return
            
        log_data = self._format_log(
            f"chunk_{state.lower()}",
            {
                "provider": provider,
                "model": model,
                "chunk": chunk
            }
        )
        self.logger.debug(json.dumps(log_data, ensure_ascii=False))

# 创建全局日志实例
logger = StructuredLogger()