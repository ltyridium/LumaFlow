"""
LRU 瓦片缓存管理器
用于管理音频频谱图的瓦片缓存，支持容量限制和自动淘汰。
"""
from collections import OrderedDict
from typing import Optional
from PySide6.QtGui import QImage


class TileCache:
    """LRU 瓦片缓存"""

    def __init__(self, max_size: int = 200):
        """
        初始化缓存

        Args:
            max_size: 最大缓存瓦片数量，默认 200
        """
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[QImage]:
        """
        获取缓存的瓦片

        Args:
            key: 缓存键

        Returns:
            QImage 如果命中，否则 None
        """
        if key in self._cache:
            # 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, image: QImage):
        """
        存入瓦片

        Args:
            key: 缓存键
            image: QImage 瓦片图像
        """
        if key in self._cache:
            # 已存在，更新并移动到末尾
            self._cache.move_to_end(key)
            self._cache[key] = image
        else:
            # 检查容量
            if len(self._cache) >= self._max_size:
                # 删除最旧的（第一个）
                self._cache.popitem(last=False)
            self._cache[key] = image

    def contains(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._cache

    def clear(self):
        """清空缓存"""
        self._cache.clear()

    def size(self) -> int:
        """返回当前缓存大小"""
        return len(self._cache)

    def keys(self):
        """返回所有缓存键"""
        return self._cache.keys()
