# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel

class ProviderConfig(BaseModel):
    base_url: str
    api_key: str
    requires_proxy: bool = False
    models: List[str]

class ConfigManager:
    def __init__(self):
        self.config_file = Path(__file__).parents[2] / "config.json"
        self.load_config()

    def load_config(self) -> Dict:
        """Load configuration file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            return self.config
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {str(e)}")

    def save_config(self) -> None:
        """Save configuration file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            raise RuntimeError(f"Failed to save config: {str(e)}")

    def get_provider(self, name: str) -> Optional[Dict]:
        """Get provider configuration"""
        return self.config.get("providers", {}).get(name)

    def add_provider(self, name: str, provider_config: ProviderConfig) -> None:
        """Add new provider"""
        if name in self.config.get("providers", {}):
            raise ValueError(f"Provider {name} already exists")

        if "providers" not in self.config:
            self.config["providers"] = {}
        if "PROVIDER_MODELS" not in self.config:
            self.config["PROVIDER_MODELS"] = {}

        self.config["providers"][name] = {
            "base_url": provider_config.base_url,
            "api_key": provider_config.api_key,
            "requires_proxy": provider_config.requires_proxy
        }
        self.config["PROVIDER_MODELS"][name] = provider_config.models
        self.save_config()

    def update_provider(self, name: str, provider_config: ProviderConfig) -> None:
        """Update provider configuration"""
        if name not in self.config.get("providers", {}):
            raise ValueError(f"Provider {name} does not exist")

        self.config["providers"][name] = {
            "base_url": provider_config.base_url,
            "api_key": provider_config.api_key,
            "requires_proxy": provider_config.requires_proxy
        }
        self.config["PROVIDER_MODELS"][name] = provider_config.models
        self.save_config()

    def delete_provider(self, name: str) -> None:
        """Delete provider"""
        if name not in self.config.get("providers", {}):
            raise ValueError(f"Provider {name} does not exist")

        del self.config["providers"][name]
        if name in self.config.get("PROVIDER_MODELS", {}):
            del self.config["PROVIDER_MODELS"][name]
        self.save_config()

config_manager = ConfigManager()
