import os
from pathlib import Path

# 获取.env文件的绝对路径
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]
env_path = project_root / '.env'

# 手动读取和解析.env文件
env_vars = {}
try:
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
                os.environ[key.strip()] = value.strip()  # 设置到环境变量
except Exception as e:
    print(f"Error reading .env file: {e}")

# 服务商支持的模型列表 | models supported by the provider
PROVIDER_MODELS = {
    "openai": ["gpt-4o", 
               "gpt-4o-mini", 
               "o3-mini"],
    "gemini": ["gemini-2.0-pro-exp-02-05", 
               "gemini-2.0-flash-exp", 
               "gemini-2.0-flash-thinking-exp"],
    "deepseek": ["deepseek-chat",
                 "deepseek-reasoner"]
}

# 接入API密钥配置
ACCESS_API_KEYS = os.getenv("ACCESS_API_KEYS", "").split(",")

# 验证必要的API密钥
if "ACCESS_API_KEYS" not in env_vars:
    raise ValueError("ACCESS_API_KEYS not found in .env file")

# 服务商配置 | provider configuration
PROVIDER_CONFIG = {
    "openai": {
        "base_url": "https://api.openai-proxy.org/v1/chat/completions",
        "api_key": env_vars.get("OPENAI_API_KEY"),
        "requires_proxy": False
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/chat/completions",
        "api_key": os.getenv("GEMINI_API_KEY"),
        "requires_proxy": True
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "requires_proxy": False
    }
}

# 代理配置 | proxy configuration    
PROXY_CONFIG = {
    "http": "socks5://127.0.0.1:7890",
    "https": "socks5://127.0.0.1:7890"
}

# 日志配置 | log configuration
LOG_CONFIG = {
    "log_file": "../logs/requests.log",
    "max_file_size": 10_485_760,  # 10MB
    "backup_count": 5,
    "log_level": "debug",  # 可选值：debug, info
    "logging_message": True
}
