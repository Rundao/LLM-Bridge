# LLM Bridge

一个用于集中管理和代理大语言模型API请求的服务。支持多个供应商的模型调用，提供统一的接口，简化了多模型使用和开发流程。

## 特性

- 🚀 统一的API接口，兼容OpenAI格式
- 🔄 支持流式(SSE)和非流式响应
- 🛠 支持多个主流大模型供应商
  - OpenAI
  - Google Gemini
  - Deepseek
  - 其他兼容OpenAI格式的供应商
- 🔌 灵活的代理配置
- 📝 详细的请求日志记录
- 🔑 API密钥管理和验证
- 📊 Token计数统计

## 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装

1. 克隆仓库
```bash
git clone https://github.com/Rundao/LLM-Bridge.git
cd llm-bridge
```

2. 安装依赖

（可选）创建conda虚拟环境
```bash
conda create -n llm-bridge python=3.12
conda activate llm-bridge
```
安装依赖
```bash
pip install -r requirements.txt
```

3. 配置环境变量
```bash
cp .env.example .env
```
编辑.env文件，填入必要的配置：
```
ACCESS_API_KEYS=your-access-key-1,your-access-key-2
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-key
DEEPSEEK_API_KEY=your-deepseek-key
```
其中`ACCESS_API_KEYS`为访问密钥，用于验证请求。
`OPENAI_API_KEY`、`GOOGLE_API_KEY`、`DEEPSEEK_API_KEY`为对应供应商的API密钥，用于调用模型。

4. 启动服务
```bash
cd src && uvicorn main:app --reload --port 1219
```
服务将在 http://localhost:1219 启动

### 修改API秘钥

如果需要修改 `.env` 文件中的API秘钥，可以使用项目根目录下的 `update_keys.sh` 脚本。

该脚本接受4个参数，分别对应要设置的4个秘钥:

1. ACCESS_API_KEYS: 访问密钥，多个密钥以逗号分隔
2. OPENAI_API_KEY: OpenAI API密钥
3. GOOGLE_API_KEY: Google API密钥  
4. DEEPSEEK_API_KEY: DeepSeek API密钥

使用示例:

```bash
./update_keys.sh "new-access-key1,new-access-key2" "new-openai-key" "new-google-key" "new-deepseek-key"
```

执行后，脚本会自动更新 `.env` 文件中对应的秘钥配置。

## API使用

### 聊天补全接口

使用curl示例：
```bash
curl http://localhost:1219/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-access-key" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

使用 [Cherry Studio](https://cherry-ai.com/) 示例：
- 在左下角点击"设置"。
- 在「模型服务」中点击"添加"，并选择「提供商类型」为 "OpenAI"。
- 在「API 密钥」字段中填写你的一个 `ACCESS_API_KEYS`。
- 在「API 地址」字段中填写 `http://127.0.0.1:1219`。
    - 部分软件（例如 [Cherry Studio](https://cherry-ai.com/)）会自动补充 `/v1/chat/completions`，请根据实际情况调整。
- 点击 "管理" 以添加模型。
- 检查连通性，开始使用。


### 支持的模型

通过前缀指定供应商，例如：
- OpenAI模型: `openai/gpt-4o`, `openai/gpt-4o-mini`
- Gemini模型: `gemini/gemini-exp-1206`
- Deepseek模型: `deepseek/deepseek-chat`

可以通过 `/v1/models` 接口获取完整的支持模型列表。

## 配置说明

### 模型列表配置

在 `src/config/config.py` 中配置支持的模型列表：

```python
PROVIDER_MODELS = {
    "openai": ["gpt-4o",
               "gpt-4o-mini",
               "o1",
               "o1-mini",
               "o3-mini"],
    "gemini": ["gemini-exp-1206",
               "gemini-2.0-flash-exp",
               "gemini-2.0-flash-thinking-exp"],
    "deepseek": ["deepseek-chat",
                 "deepseek-reasoner"]
}
```

每个供应商下可以配置多个支持的模型，用户在请求时通过 `供应商/模型名` 的格式来指定使用的模型。

### 供应商配置

在 `src/config/config.py` 中配置供应商信息：

```python
PROVIDER_CONFIG = {
    "openai": {
        "base_url": "https://api.openai-proxy.org/v1/chat/completions",
        "api_key": env_vars.get("OPENAI_API_KEY"),
        "requires_proxy": False
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/chat/completions",
        "api_key": os.getenv("GOOGLE_API_KEY"),
        "requires_proxy": True
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "requires_proxy": False
    }
}
```

每个供应商的配置包括：
- `base_url`: API请求地址
- `api_key`: 从环境变量获取的API密钥
- `requires_proxy`: 是否需要使用代理

### 代理配置

在 `src/config/config.py` 中配置代理：

```python
PROXY_CONFIG = {
    "http": "socks5://127.0.0.1:7890",
    "https": "socks5://127.0.0.1:7890"
}
```

### 日志配置

日志文件位于 `logs/requests.log`，可在配置文件中调整：

```python
LOG_CONFIG = {
    "log_file": "logs/requests.log",
    "max_file_size": 10485760,  # 10MB
    "backup_count": 5,
    "log_level": "debug"
}
```

## 开发说明

### 项目结构

```
.
├── src/
│   ├── main.py           # 主入口
│   ├── api/
│   │   └── router.py     # 请求路由处理
│   ├── config/
│   │   └── config.py     # 配置文件
│   └── core/
│       ├── logger.py     # 日志处理
│       └── token_counter.py  # Token计数
├── logs/
│   └── requests.log      # 请求日志
├── update_api_keys.py    # 修改API秘钥的脚本
├── update_keys.sh        # 修改API秘钥的shell脚本
├── .env                  # 环境变量
└── requirements.txt      # 项目依赖
```

### 添加新的模型供应商

1. 在 `PROVIDER_MODELS` 中添加供应商支持的模型列表
2. 在 `PROVIDER_CONFIG` 中添加供应商配置
3. 确保在 `.env` 中添加对应的 API 密钥

## TODOs

计划开发的功能：

### 1. 消费统计功能
- [ ] 多模态模型token计数
- [ ] Token用量统计和分析
- [ ] 按模型统计调用次数和费用
- [ ] 可视化图表展示使用情况
- [ ] 导出统计报告

### 2. WebUI管理界面
- [ ] 可视化配置界面
- [ ] 实时监控请求状态
- [ ] 系统运行状态展示

### 3. 接口与适配
- [ ] 支持其他OpenAI兼容的接口
- [ ] 适配不同供应商的请求响应格式
- [ ] 统一的错误处理和状态码映射

### 4. 其他优化
- [ ] 请求速率限制
- [ ] 自动故障转移
- [ ] 性能监控和报警
- [ ] 缓存机制优化

## 许可证

MIT License

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进项目。
