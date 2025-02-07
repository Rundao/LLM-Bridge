import aiohttp
import time
import json
import uuid
from typing import Optional, Dict, Any, AsyncGenerator
from config.config import PROVIDER_CONFIG, PROXY_CONFIG, ACCESS_API_KEYS, PROVIDER_MODELS
from core.logger import logger
from core.token_counter import token_counter

# 模型名称解析
def parse_model_name(model: str) -> tuple[str, str]:
    """解析模型名称，返回(provider_name, model_name)元组"""
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider, model_name
    # 默认使用deepseek
    return "deepseek", model

class Router:
    def __init__(self):
        self.session = None

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _validate_request(self, model: str, api_key: str, payload: Dict[str, Any]):
        """验证请求参数并返回必要的配置信息"""
        # 解析模型名称
        provider, model_name = parse_model_name(model)
        self.model = model_name
        
        # 验证服务商是否存在
        if provider not in PROVIDER_CONFIG:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Unsupported provider: {provider}",
                messages=payload.get("messages", [])
            )
            raise ValueError(f"Unsupported provider: {provider}")

        # 验证模型是否在服务商支持的模型列表中
        if model_name not in PROVIDER_MODELS.get(provider, []):
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=400,
                error_message=f"Model {model_name} not supported by provider {provider}",
                messages=payload.get("messages", [])
            )
            raise ValueError(f"Model {model_name} not supported by provider {provider}")

        provider_config = PROVIDER_CONFIG.get(provider)

        # 验证接入API密钥
        if api_key not in ACCESS_API_KEYS:
            logger.log_request_error(
                provider="unknown",
                model=model,
                status_code=401,
                error_message="Invalid access API key",
                messages=payload.get("messages", [])
            )
            raise PermissionError("Invalid access API key")

        # 获取服务商配置
        if not provider_config:
            logger.log_request_error(
                provider="unknown",
                model=model,
                status_code=400,
                error_message=f"Provider not configured for model: {model}",
                messages=payload.get("messages", [])
            )
            raise ValueError(f"Provider not configured for model: {model}")

        return provider, provider_config

    async def _prepare_request(self, provider_config: Dict[str, Any], payload: Dict[str, Any]):
        """准备请求参数"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider_config['api_key']}"
        }
        
        if not isinstance(payload, dict):
            payload = dict(payload)

        # 如果需要代理,只返回 https 代理地址字符串
        proxy = PROXY_CONFIG["https"] if provider_config["requires_proxy"] else None
        return headers, proxy

    async def route_request_stream(self, model: str, api_key: str, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """处理流式请求，支持 SSE 协议"""
        
        provider, provider_config = await self._validate_request(model, api_key, payload)
        headers, proxies = await self._prepare_request(provider_config, payload)
        payload["model"] = self.model  # 修改 payload 中 model 字段
        messages = payload.get("messages", [])
        input_tokens = token_counter.count_message_tokens(messages, self.model)
        logger.log_request_start(provider, model, messages, is_stream=True, input_tokens=input_tokens)

        try:
            start_time = time.time()
            session = await self.get_session()
            async with session.post(
                provider_config['base_url'],
                json=payload,
                headers=headers,
                proxy=proxies
            ) as response:
                full_response = []      # 用于累计所有有效文本
                buffer = ""             # 保存数据缓冲
                current_event = []      # 收集当前 SSE 事件行

                # 遍历每个数据块，注意 decode 时使用 errors='replace'
                async for chunk in response.content:
                    if chunk:
                        buffer += chunk.decode("utf-8", errors="replace")
                        logger.log_chunk(provider, model, buffer)
                        
                        # 逐行处理，注意可能存在残留未完整一行的数据
                        while True:
                            newline_pos = buffer.find("\n")
                            if newline_pos == -1:
                                break
                            line = buffer[:newline_pos].strip()
                            buffer = buffer[newline_pos + 1:]
                            
                            # 空行表示当前 SSE 事件结束
                            if line == "":
                                if current_event:
                                    # 合并当前事件数据
                                    event_data = "\n".join(current_event)
                                    current_event = []
                                    
                                    # 如果是结束标识 [DONE]，则跳过
                                    if event_data == "[DONE]":
                                        continue

                                    try:
                                        msg_data = json.loads(event_data)
                                        # 如果解析结果含有 choices 部分，则提取 content 字段
                                        if "choices" in msg_data and msg_data["choices"]:
                                            delta = msg_data["choices"][0].get("delta", {})
                                            content = delta.get("content")
                                            if content is not None:
                                                full_response.append(content)
                                        # 检查是否存在id，不存在则添加
                                        if "id" not in msg_data:
                                            msg_data["id"] = str(uuid.uuid4())
                                        # 转发符合 SSE 格式的完整事件
                                        yield f"data: {json.dumps(msg_data)}\n\n"
                                    except (json.JSONDecodeError, IndexError, KeyError) as e:
                                        # 仅记录日志，不直接将错误信息暴露给客户端；
                                        logger.log_request_error(
                                            provider=provider,
                                            model=model,
                                            status_code=500,
                                            error_message=f"解析流数据错误: {str(e)}",
                                            messages=messages
                                        )
                                        # 可选择转发一个标准错误提示（也可以选择不转发）
                                        yield f"data: {json.dumps({'error': '解析数据异常'})}\n\n"
                                continue
                            
                            # 跳过以 ":" 开头的注释/心跳行（如 ": keep-alive"）
                            if line.startswith(":"):
                                logger.logger.debug(f"Received SSE heartbeat: {line[1:].strip()}")
                                continue
                            
                            # 只处理以 "data:" 开头的有效行；其他行直接加入到当前事件中
                            if line.startswith("data:"):
                                data_content = line[len("data:"):].strip()
                                current_event.append(data_content)
                            else:
                                current_event.append(line)
                
                # 流结束后，若 buffer 中仍有数据，则尝试处理或发出警告
                if buffer.strip():
                    logger.logger.warning("Stream ended but received incomplete data in buffer.")
                    yield f"data: {json.dumps({'warning': 'incomplete data'})}\n\n"

                duration = time.time() - start_time
                complete_response = "".join(full_response)
                output_tokens = token_counter.count_completion_tokens(complete_response, self.model)
                logger.log_request_complete(
                    provider=provider,
                    model=model,
                    status_code=response.status,
                    duration=duration,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    messages=messages,
                    response=complete_response,
                    is_stream=True
                )
        except Exception as e:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=500,
                error_message=str(e),
                messages=messages
            )
            raise

    async def route_request(self, model: str, api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理非流式请求"""
        if payload.get("stream", False):
            raise ValueError("Use route_request_stream for streaming requests")
            
        provider, provider_config = await self._validate_request(model, api_key, payload)
        headers, proxies = await self._prepare_request(provider_config, payload)
        
        # 修改 payload 中的 model 字段
        payload["model"] = self.model
        
        messages = payload.get("messages", [])
        input_tokens = token_counter.count_message_tokens(messages, self.model)
        
        # 记录请求开始
        logger.log_request_start(provider, model, messages, is_stream=False, input_tokens=input_tokens)
        
        try:
            start_time = time.time()
            session = await self.get_session()
            async with session.post(
                provider_config['base_url'],
                json=payload,
                headers=headers,
                proxy=proxies
            ) as response:
                response_data = await response.json()
                duration = time.time() - start_time

                completion_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                output_tokens = token_counter.count_completion_tokens(completion_text, self.model)

                logger.log_request_complete(
                    provider=provider,
                    model=model,
                    status_code=response.status,
                    duration=duration,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    messages=messages,
                    response=response_data,
                    is_stream=False
                )

                return response_data
        except Exception as e:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=500,
                error_message=str(e),
                messages=messages
            )
            raise
        except aiohttp.ClientError as e:
            error_msg = f"API request failed: {str(e)}"
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=500,
                error_message=error_msg,
                messages=messages
            )
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=500,
                error_message=error_msg,
                messages=messages
            )
            raise RuntimeError(error_msg)

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None