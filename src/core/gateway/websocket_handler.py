"""
WebSocket处理器
处理WebSocket连接，支持双向实时通信
"""
from typing import Dict, Any, Set
from fastapi import WebSocket, WebSocketDisconnect
from ..router import Router
from infrastructure.logging import logger
import json
import asyncio
import uuid
from datetime import datetime

class WebSocketHandler:
    """WebSocket连接处理器"""
    
    def __init__(self, router: Router):
        self.router = router
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_times: Dict[str, datetime] = {}
    
    def _get_client_addr(self, websocket: WebSocket) -> str:
        """获取客户端地址，包含端口号"""
        client = websocket.client
        if client and client.host:
            return f"{client.host}:{client.port}"
        return None
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """
        处理新的WebSocket连接
        
        Args:
            websocket: WebSocket连接对象
            client_id: 客户端ID
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_times[client_id] = datetime.now()
        client_addr = self._get_client_addr(websocket)
        
        logger.log_message(
            message=f"WebSocket client connected",
            provider="system",
            request_id=client_id,
            client_addr=client_addr
        )
    
    def disconnect(self, client_id: str):
        """
        处理WebSocket断开连接
        
        Args:
            client_id: 客户端ID
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_times:
            del self.connection_times[client_id]
            
        logger.log_message(
            message=f"WebSocket client disconnected",
            provider="system",
            request_id=client_id
        )
    
    async def handle_message(self, websocket: WebSocket, client_id: str):
        """
        处理WebSocket消息
        
        Args:
            websocket: WebSocket连接对象
            client_id: 客户端ID
        """
        client_addr = self._get_client_addr(websocket)
        
        try:
            while True:
                # 接收消息
                message = await websocket.receive_json()
                
                # 验证消息格式
                if not isinstance(message, dict):
                    await self._send_error(
                        websocket,
                        "Invalid message format",
                        request_id=client_id,
                        client_addr=client_addr
                    )
                    continue
                
                # 处理不同类型的消息
                message_type = message.get("type")
                if message_type == "chat":
                    await self._handle_chat_message(
                        websocket,
                        client_id,
                        message,
                        client_addr
                    )
                else:
                    await self._send_error(
                        websocket,
                        f"Unknown message type: {message_type}",
                        request_id=client_id,
                        client_addr=client_addr
                    )
                    
        except WebSocketDisconnect:
            self.disconnect(client_id)
        except Exception as e:
            logger.log_request_error(
                provider="system",
                model="none",
                status_code=500,
                error_message=str(e),
                request_id=client_id,
                client_addr=client_addr
            )
            await self._send_error(
                websocket,
                str(e),
                request_id=client_id,
                client_addr=client_addr
            )
    
    async def _handle_chat_message(
        self,
        websocket: WebSocket,
        client_id: str,
        message: Dict[str, Any],
        client_addr: str
    ):
        """处理聊天消息"""
        try:
            # 验证必要字段
            payload = message.get("payload", {})
            model = payload.get("model")
            api_key = message.get("api_key", "").replace("Bearer ", "")
            
            if not model or not api_key:
                await self._send_error(
                    websocket,
                    "Missing required fields",
                    request_id=client_id,
                    client_addr=client_addr
                )
                return
            
            # 设置流式输出
            payload["stream"] = True
            
            # 记录请求开始
            logger.log_request_start(
                provider="unknown",
                model=model,
                messages=payload.get("messages", []),
                is_stream=True,
                request_id=client_id,
                client_addr=client_addr
            )
            
            # 处理流式响应
            async for chunk in self.router.route_request_stream(
                model,
                api_key,
                payload,
                request_id=client_id,
                client_addr=client_addr
            ):
                if chunk.strip():
                    await websocket.send_text(chunk)
                    logger.log_chunk(
                        chunk=chunk,
                        provider="unknown",
                        model=model,
                        state="sent",
                        request_id=client_id
                    )
            
            # 发送完成标记
            await websocket.send_text("data: [DONE]\n\n")
            
        except Exception as e:
            error_message = {
                "error": {
                    "message": str(e),
                    "type": e.__class__.__name__
                }
            }
            await websocket.send_text(f"data: {json.dumps(error_message)}\n\n")
            await websocket.send_text("data: [DONE]\n\n")
            
            logger.log_request_error(
                provider="unknown",
                model=model if model else "unknown",
                status_code=500,
                error_message=str(e),
                request_id=client_id,
                client_addr=client_addr
            )
    
    async def _send_error(
        self,
        websocket: WebSocket,
        message: str,
        request_id: str,
        client_addr: str = None
    ):
        """发送错误消息"""
        error_data = {
            "error": {
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
        }
        await websocket.send_json(error_data)
        
        logger.log_request_error(
            provider="system",
            model="none",
            status_code=400,
            error_message=message,
            request_id=request_id,
            client_addr=client_addr
        )
    
    async def broadcast(self, message: str):
        """
        广播消息给所有连接的客户端
        
        Args:
            message: 要广播的消息
        """
        disconnected_clients = set()
        
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected_clients.add(client_id)
                logger.log_message(
                    message="Failed to send broadcast message",
                    provider="system",
                    request_id=client_id
                )
        
        # 清理断开的连接
        for client_id in disconnected_clients:
            self.disconnect(client_id)
    
    def get_active_connections_count(self) -> int:
        """获取活动连接数"""
        return len(self.active_connections)