from typing import Optional, Dict, Any

import httpx
import urllib3

from utils.logger import logger


class NetworkManager:
    """网络请求管理类"""

    def __init__(self):
        self.client = self._setup_client()
        self.async_client = None

    def _setup_client(self) -> httpx.Client:
        """配置同步客户端"""
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return httpx.Client(verify=False, trust_env=False, timeout=10.0)

    async def _ensure_async_client(self):
        """确保异步客户端存在"""
        if self.async_client is None:
            self.async_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=100,
                                                                      max_keepalive_connections=20),
                                                  verify=False,
                                                  trust_env=False,
                                                  timeout=10.0)
        return self.async_client

    async def close(self):
        """关闭异步客户端"""
        if self.async_client:
            await self.async_client.aclose()
            self.async_client = None

    def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """发送同步GET请求"""
        try:
            return self.client.get(url, **kwargs)
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return None

    async def async_get(self, url: str, params: Optional[Dict] = None,
                        headers: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """发送异步GET请求"""
        try:
            client = await self._ensure_async_client()
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                return None
            return response.json()
        except Exception as e:
            logger.error(f"异步请求失败: {e}")
            return None

    async def async_get_text(self, url: str, params: Optional[Dict] = None,
                             headers: Optional[Dict] = None) -> Optional[str]:
        """发送异步GET请求并返回文本"""
        try:
            client = await self._ensure_async_client()
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                return None
            return response.text
        except Exception as e:
            logger.error(f"异步请求失败: {e}")
            return None

    async def async_post(self, url: str, data: Optional[Dict] = None,
                         headers: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """发送异步POST请求"""
        try:
            client = await self._ensure_async_client()
            response = await client.post(url, data=data, headers=headers)
            if response.status_code != 200:
                return None
            return response.json()
        except Exception as e:
            logger.error(f"异步请求失败: {e}")
            return None

    async def async_get_bytes(self, url: str, headers: Optional[Dict] = None) -> Optional[bytes]:
        """发送异步GET请求并返回二进制数据"""
        try:
            client = await self._ensure_async_client()
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            return response.read()
        except Exception as e:
            logger.error(f"异步请求失败: {e}")
            return None

    def close_sync(self):
        """关闭同步客户端"""
        if self.client:
            self.client.close()


# 全局网络管理器实例
network = NetworkManager()
