# LLM Bridge

[English](README.md) | [简体中文](docs/README-zh-CN.md)

LLM Bridge is a centralized service for managing and proxying API requests to large language models. It supports multiple providers and offers a unified API interface, simplifying the process of using and developing with various models.

## Features

- 🚀 Unified API interface compatible with OpenAI's format
- 🔄 Supports both streaming (SSE) and non-streaming responses
- 🛠 Supports multiple popular LLM providers:
  - OpenAI
  - Google Gemini
  - Deepseek
  - Other providers compatible with the OpenAI format
- 🔌 Flexible proxy configuration
- 📝 Detailed request logging
- 🔑 API key management and authentication
- 📊 Token counting and usage statistics

## Quick Start

### Prerequisites

- Python 3.8+
- pip

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Rundao/LLM-Bridge.git
   cd llm-bridge
   ```

2. Install dependencies

   (Optional) Create a conda virtual environment:
   ```bash
   conda create -n llm-bridge python=3.12
   conda activate llm-bridge
   ```
   Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables
   ```bash
   cp .env.example .env
   ```
   Then edit the `.env` file and fill in the necessary configurations:
   ```
   ACCESS_API_KEYS=your-access-key-1,your-access-key-2
   OPENAI_API_KEY=your-openai-key
   GOOGLE_API_KEY=your-google-key
   DEEPSEEK_API_KEY=your-deepseek-key
   ```
   Here, `ACCESS_API_KEYS` is used for authenticating API requests.
   `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and `DEEPSEEK_API_KEY` correspond to the API keys for each provider.

4. Start the service
   ```bash
   cd src && uvicorn main:app --reload --port 1219
   ```
   The service will be available at http://localhost:1219.

## API Usage

### Chat Completion Endpoint

Example using curl:
```bash
curl http://localhost:1219/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-access-key" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

Example using [Cherry Studio](https://cherry-ai.com/):
- Click "Settings" in the bottom left corner.
- In "Model Provider", click "Add" and choose Provider Type as "OpenAI".
- Enter one of your `ACCESS_API_KEYS` in the "API Key" field.
- Enter `http://127.0.0.1:1219` in the "API URL" field.
    - Some software (such as [Cherry Studio](https://cherry-ai.com/)) will automatically supplement `/v1/chat/completions`, please adjust according to the actual situation
- Click "Manage" to add models.
- Check the connectivity and start using it.

### Supported Models

Specify the provider by prefixing the model name. For example:
- OpenAI models: `openai/gpt-4o`, `openai/gpt-4o-mini`
- Gemini models: `gemini/gemini-exp-1206`
- Deepseek models: `deepseek/deepseek-chat`

You can use the `/v1/models` endpoint to retrieve a complete list of supported models.

## Configuration Details

### Model List Configuration

Configure the list of supported models in `src/config/config.py`:
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
Each provider can have multiple supported models. Users can specify the model using the format `provider/model-name`.

### Provider Configuration

Configure provider information in `src/config/config.py`:
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
Each provider configuration includes:
- `base_url`: API request URL.
- `api_key`: API key obtained from environment variables.
- `requires_proxy`: A flag indicating whether a proxy should be used.

### Proxy Configuration

Configure proxy settings in `src/config/config.py`:
```python
PROXY_CONFIG = {
    "http": "socks5://127.0.0.1:7890",
    "https": "socks5://127.0.0.1:7890"
}
```

### Logging Configuration

Logs are stored in `logs/requests.log`. Adjust the settings in the configuration file if needed:
```python
LOG_CONFIG = {
    "log_file": "logs/requests.log",
    "max_file_size": 10485760,  # 10MB
    "backup_count": 5,
    "log_level": "debug"
}
```

## Development Guidelines

### Project Structure

```
.
├── src/
│   ├── main.py           # Main entry point
│   ├── api/
│   │   └── router.py     # Request routing handling
│   ├── config/
│   │   └── config.py     # Configuration file
│   └── core/
│       ├── logger.py     # Logging handler
│       └── token_counter.py  # Token counting utility
├── logs/
│   └── requests.log      # Request logs
├── .env                  # Environment variables
└── requirements.txt      # Project dependencies
```

### Adding a New Model Provider

1. Add the supported models for the provider in `PROVIDER_MODELS`.
2. Include the provider's configuration in `PROVIDER_CONFIG`.
3. Ensure the corresponding API key is added to your `.env` file.

## TODOs

Planned features for upcoming versions:

### 1. Usage Statistics
- [ ] Token counting for multimodal models
- [ ] Token usage statistics and analysis
- [ ] Call count and cost statistics per model
- [ ] Visual charts to display usage
- [ ] Exportable reports

### 2. WebUI Management Interface
- [ ] A visual configuration dashboard
- [ ] Real-time request monitoring
- [ ] System status display

### 3. Format Conversion and Adaptation
- [ ] Support other OpenAI-compatible APIs
- [ ] Adapt to various providers' request/response formats
- [ ] Unified error handling and status code mapping

### 4. Additional Optimizations
- [ ] Request rate limiting
- [ ] Automatic failover
- [ ] Performance monitoring and alerts
- [ ] Caching improvements

## License

MIT License

## Contributing

Contributions are welcome! Please submit your issues and pull requests to help improve the project.