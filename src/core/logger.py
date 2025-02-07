import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import json
from config.config import LOG_CONFIG
import os

class RequestLogger:
    def __init__(self):
        self.logger = logging.getLogger("LLM_Bridge")
        
        # 从配置读取日志级别
        log_level = LOG_CONFIG.get("log_level", "info").upper()
        self.logger.setLevel(getattr(logging, log_level))

        # 检查log的文件路径是否存在，如果不存在则创建
        log_dir = os.path.dirname(LOG_CONFIG["log_file"])
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 配置日志轮转
        handler = RotatingFileHandler(
            LOG_CONFIG["log_file"],
            maxBytes=LOG_CONFIG["max_file_size"],
            backupCount=LOG_CONFIG["backup_count"]
        )
        
        formatter = logging.Formatter(
            "==== %(asctime)s | %(levelname)s ====\n%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def log_request_start(self, provider, model, messages, is_stream=False, input_tokens=None):
        """记录请求开始"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "request_start",
            "provider": provider,
            "model": model,
            "is_stream": is_stream,
            "input_tokens": input_tokens,
            "messages": messages
        }
        if LOG_CONFIG.get("logging_message", False):
            self.logger.info(json.dumps(log_data, ensure_ascii=False))
        else:
            # 只记录基本信息
            basic_data = {k: v for k, v in log_data.items() if k != "messages"}
            self.logger.info(json.dumps(basic_data, ensure_ascii=False))
        
    def log_chunk(self, provider, model, chunk):
        """记录流式响应的chunk"""
        if self.logger.level > logging.DEBUG:
            return
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "chunk",
            "provider": provider,
            "model": model,
            "chunk": chunk
        }
        self.logger.debug(json.dumps(log_data, ensure_ascii=False))

    def log_request_complete(self, provider, model, status_code, duration, input_tokens, output_tokens, messages, response, is_stream=False):
        """记录请求完成"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "request_complete",
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
        if LOG_CONFIG.get("logging_message", False):
            self.logger.info(json.dumps(log_data, ensure_ascii=False))
        else:
            # 只记录统计信息
            basic_data = {
                "timestamp": log_data["timestamp"],
                "event": log_data["event"],
                "provider": provider,
                "model": model,
                "status_code": status_code,
                "duration": duration,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "is_stream": is_stream
            }
            self.logger.info(json.dumps(basic_data, ensure_ascii=False))

    def log_request_error(self, provider, model, status_code, error_message, messages=None):
        """记录请求错误"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event": "request_error",
            "provider": provider,
            "model": model,
            "status_code": status_code,
            "error": error_message
        }
        if messages and LOG_CONFIG.get("logging_message", False):
            log_data["messages"] = messages
        self.logger.error(json.dumps(log_data, ensure_ascii=False))
    
    # 兼容旧的接口
    def log_request(self, provider, model, status_code, duration, input_tokens, output_tokens, messages, response):
        self.log_request_complete(
            provider, model, status_code, duration,
            input_tokens, output_tokens, messages, response
        )

    def get_logs(self, start_time=None, end_time=None, provider=None):
        logs = []
        with open(LOG_CONFIG["log_file"], "r") as f:
            for line in f:
                log = json.loads(line.strip())
                if self._filter_log(log, start_time, end_time, provider):
                    logs.append(log)
        return logs

    def _filter_log(self, log, start_time, end_time, provider):
        log_time = datetime.fromisoformat(log["timestamp"])
        if start_time and log_time < start_time:
            return False
        if end_time and log_time > end_time:
            return False
        if provider and log["provider"] != provider:
            return False
        return True



# 单例日志实例
logger = RequestLogger()