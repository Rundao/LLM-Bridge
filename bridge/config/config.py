import os
import json
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

# 从config.json加载配置
config_path = project_root / "config.json"
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        PROVIDER_MODELS = config_data.get("PROVIDER_MODELS", {})
        PROVIDER_CONFIG = {}
        
        # 处理每个provider的配置
        for provider, config in config_data.get("providers", {}).items():
            PROVIDER_CONFIG[provider] = {
                "base_url": config.get("base_url"),
                "api_key": config.get("api_key"),
                "requires_proxy": config.get("requires_proxy", False)
            }
except Exception as e:
    print(f"Error reading config.json: {e}")
    PROVIDER_MODELS = {}
    PROVIDER_CONFIG = {}

# 接入API密钥配置
ACCESS_API_KEYS = os.getenv("ACCESS_API_KEYS", "").split(",")

# 验证必要的API密钥
if not ACCESS_API_KEYS or not ACCESS_API_KEYS[0]:
    raise ValueError("ACCESS_API_KEYS not found in .env file")

# 代理配置 | proxy configuration    
PROXY_CONFIG = {
    "http": "socks5://127.0.0.1:7890",
    "https": "socks5://127.0.0.1:7890"
}

# 日志配置 | log configuration
LOG_CONFIG = {
    "log_file": str(project_root / "logs/requests.log"),
    "max_file_size": 10485760,  # 10MB
    "backup_count": 5,
    "log_level": "debug",  # 可选值：debug, info
    "logging_message": True
}
