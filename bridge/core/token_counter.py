import tiktoken
from typing import List, Dict, Any

class TokenCounter:
    def __init__(self):
        self.encoders = {}

    def get_encoder(self, model: str):
        if model not in self.encoders:
            try:
                self.encoders[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                # 如果模型不在tiktoken中，使用cl100k_base作为默认编码器
                self.encoders[model] = tiktoken.get_encoding("cl100k_base")
        return self.encoders[model]

    def count_message_tokens(self, messages: List[Dict[str, Any]], model: str) -> int:
        """计算消息列表的token数量"""
        encoder = self.get_encoder(model)
        total_tokens = 0
        
        for message in messages:
            # 每条消息的基础token（根据不同模型可能有所不同）
            total_tokens += 4  # 每条消息的元数据开销
            
            for key, value in message.items():
                encoded_value = 0
                if key == "name":  
                    # 处理name字段
                    total_tokens += 1  # name字段开销
                    encoded_value = len(encoder.encode(str(value)))
                elif key == "content":
                    # 处理content字段（支持多种格式）
                    if isinstance(value, list):
                        # 处理OpenAI风格的多内容消息
                        text_parts = []
                        for item in value:
                            if isinstance(item, dict):
                                # 提取text类型的内容
                                if item.get("type") == "text" and "text" in item:
                                    text_parts.append(str(item["text"]))
                        content_str = " ".join(text_parts)
                    else:
                        # 处理字符串、数字、None等类型
                        content_str = str(value) if value is not None else ""
                    
                    encoded_value = len(encoder.encode(content_str))
                elif key == "role":
                    # 处理role字段
                    total_tokens += 1  # role字段开销
                    encoded_value = len(encoder.encode(str(value)))
                
                total_tokens += encoded_value
                
        total_tokens += 2  # 消息列表的开始和结束标记
        return total_tokens

    def count_completion_tokens(self, completion: str, model: str) -> int:
        """计算完成内容的token数量"""
        encoder = self.get_encoder(model)
        return len(encoder.encode(completion))

# 创建全局实例
token_counter = TokenCounter()