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
                if key == "name":  # 如果消息中包含name字段
                    total_tokens += 1  # name字段的开销
                    total_tokens += len(encoder.encode(value))
                elif key == "content":  # content字段
                    total_tokens += len(encoder.encode(value))
                elif key == "role":  # role字段
                    total_tokens += 1  # role字段的开销
                    total_tokens += len(encoder.encode(value))
                    
        total_tokens += 2  # 消息列表的开始和结束标记
        return total_tokens

    def count_completion_tokens(self, completion: str, model: str) -> int:
        """计算完成内容的token数量"""
        encoder = self.get_encoder(model)
        return len(encoder.encode(completion))

# 创建全局实例
token_counter = TokenCounter()