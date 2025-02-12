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
            timeout = aiohttp.ClientTimeout(
                total=600,  # 总超时时间 10 分钟
                connect=30,  # 连接超时 30 秒
                sock_read=180  # 读取超时 3 分钟
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def _validate_request(self, model: str, api_key: str, payload: Dict[str, Any]):
        """验证请求参数并返回必要的配置信息"""
        
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

        # 获取服务商配置
        provider_config = PROVIDER_CONFIG.get(provider)
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

        start_time = time.time()
        response = None

        try:
            session = await self.get_session()
            response = await session.post(
                provider_config['base_url'],
                json=payload,
                headers=headers,
                proxy=proxies,
                timeout=aiohttp.ClientTimeout(total=600, connect=30, sock_read=180)
            )

            if response.status != 200:
                error_text = await response.text()
                logger.log_request_error(
                    provider=provider,
                    model=model,
                    status_code=response.status,
                    error_message=f"API返回错误状态码: {response.status}, 详细信息: {error_text}",
                    messages=messages
                )
                raise RuntimeError(f"API返回错误状态码: {response.status}")

            buffer = ""             # 保存数据缓冲
            current_sse = {         # 当前SSE事件的状态
                'event': None,      # 事件类型
                'data': [],         # 数据行列表
                'id': None,         # 事件ID
                'retry': None       # 重试间隔
            }
            full_response = []      # 用于累计所有有效文本

            async for chunk in response.content:
                if chunk:
                    buffer += chunk.decode("utf-8", errors="replace")
                    logger.log_chunk(buffer, provider, model)
                    
                    while True:
                        newline_pos = buffer.find("\n")
                        if newline_pos == -1:
                            break
                            
                        line = buffer[:newline_pos].strip()
                        buffer = buffer[newline_pos + 1:]
                        
                        # 空行表示事件结束，处理完整事件
                        if line == "":
                            if current_sse['data']:
                                try:
                                    # 合并多行数据
                                    event_data = "\n".join(current_sse['data'])
                                    
                                    # 处理特殊的[DONE]标记
                                    if event_data == "[DONE]":
                                        yield "data: [DONE]\n\n"
                                        current_sse = {'event': None, 'data': [], 'id': None, 'retry': None}
                                        continue

                                    msg_data = json.loads(event_data)
                                    
                                    # 处理内容
                                    if "choices" in msg_data and msg_data["choices"]:
                                        delta = msg_data["choices"][0].get("delta", {})
                                        content = delta.get("content")
                                        if content is not None:
                                            full_response.append(content)

                                    # 构建SSE响应
                                    sse_lines = []
                                    if current_sse['event']:
                                        sse_lines.append(f"event: {current_sse['event']}")
                                    
                                    event_id = current_sse['id'] or str(uuid.uuid4())
                                    sse_lines.append(f"id: {event_id}")
                                    
                                    if current_sse['retry']:
                                        sse_lines.append(f"retry: {current_sse['retry']}")
                                    
                                    sse_lines.append(f"data: {json.dumps(msg_data)}")
                                    yield f"{chr(10).join(sse_lines)}\n\n"

                                except (json.JSONDecodeError, IndexError, KeyError) as e:
                                    logger.log_request_error(
                                        provider=provider,
                                        model=model,
                                        status_code=500,
                                        error_message=f"解析流数据错误: {str(e)}",
                                        messages=messages
                                    )
                                    yield f"data: {json.dumps({'error': '解析数据异常'})}\n\n"
                            
                            # 重置当前事件
                            current_sse = {'event': None, 'data': [], 'id': None, 'retry': None}
                            continue

                        # 处理SSE字段
                        if line.startswith(":"):  # 注释行
                            yield f"{line}\n"
                            continue
                            
                        # 使用startswith判断SSE字段
                        if line.startswith("event:"):
                            current_sse['event'] = line[6:].strip()
                        elif line.startswith("data:"):
                            current_sse['data'].append(line[5:].strip())
                        elif line.startswith("id:"):
                            current_sse['id'] = line[3:].strip()
                        elif line.startswith("retry:"):
                            try:
                                current_sse['retry'] = int(line[6:].strip())
                            except ValueError:
                                pass
                        elif ":" not in line and line.strip():
                            # 没有冒号的非空行视为data字段的延续
                            current_sse['data'].append(line)
                        else:
                            # 未知字段记录警告
                            if line.strip():
                                logger.logger.warning(f"未知的SSE字段: {line}")

            # 处理残留在buffer中的数据
            if buffer.strip():
                logger.logger.warning("Stream ended but received incomplete data in buffer.")
                yield f"data: {json.dumps({'warning': 'incomplete data'})}\n\n"

        except Exception as e:
            logger.log_request_error(
                provider=provider,
                model=model,
                status_code=500,
                error_message=str(e),
                messages=messages
            )
            raise

        finally:
            # 记录完成状态
            duration = time.time() - start_time
            complete_response = "".join(full_response)
            output_tokens = token_counter.count_completion_tokens(complete_response, self.model)
            
            logger.log_request_complete(
                provider=provider,
                model=model,
                status_code=response.status if response else 500,
                duration=duration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                messages=messages,
                response=complete_response,
                is_stream=True
            )

            # 安全地关闭响应
            if response and not response.closed:
                await response.close()

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
                proxy=proxies,
                timeout=aiohttp.ClientTimeout(total=600, connect=30, sock_read=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.log_request_error(
                        provider=provider,
                        model=model,
                        status_code=response.status,
                        error_message=f"API返回错误状态码: {response.status}, 详细信息: {error_text}",
                        messages=messages
                    )
                    raise RuntimeError(f"API返回错误状态码: {response.status}")

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