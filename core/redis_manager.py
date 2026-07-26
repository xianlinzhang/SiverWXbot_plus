import json
import os
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import redis
    from redis.connection import ConnectionPool
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None
    RedisError = Exception
    RedisConnectionError = Exception


class RedisManager:
    def __init__(self, config):
        if hasattr(config, 'redis_host'):
            self.config = {
                'host': getattr(config, 'redis_host', 'localhost'),
                'port': getattr(config, 'redis_port', 6379),
                'db': getattr(config, 'redis_db', 0),
                'password': getattr(config, 'redis_password', None),
                'timeout': getattr(config, 'redis_timeout', 5),
                'retry_count': getattr(config, 'redis_retry_count', 3),
                'fallback': getattr(config, 'redis_fallback', True),
                'fallback_path': getattr(config, 'redis_fallback_path', './fallback_redis.json')
            }
        elif hasattr(config, 'get'):
            self.config = {
                'host': config.get('host', 'localhost'),
                'port': config.get('port', 6379),
                'db': config.get('db', 0),
                'password': config.get('password', None),
                'timeout': config.get('timeout', 5),
                'retry_count': config.get('retry_count', 3),
                'fallback': config.get('fallback', True),
                'fallback_path': config.get('fallback_path', './fallback_redis.json')
            }
        else:
            self.config = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'password': None,
                'timeout': 5,
                'retry_count': 3,
                'fallback': True,
                'fallback_path': './fallback_redis.json'
            }
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._fallback_data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._is_available = False
        self._logger = logging.getLogger(__name__)
        try:
            self._init_client()
        except Exception as e:
            self._logger.error(f"RedisManager 初始化失败: {e}")

    def _init_client(self) -> None:
        if not REDIS_AVAILABLE:
            self._logger.warning("redis-py not installed, falling back to local storage")
            self._is_available = False
            self._load_fallback_data()
            return

        try:
            self._pool = ConnectionPool(
                host=self.config['host'],
                port=self.config['port'],
                db=self.config['db'],
                password=self.config['password'],
                socket_timeout=self.config['timeout'],
                socket_connect_timeout=self.config['timeout']
            )
            self._client = redis.Redis(connection_pool=self._pool)
            if self._test_connection():
                self._is_available = True
                self._logger.info(f"Redis connection established: {self.config['host']}:{self.config['port']}/db{self.config['db']}")
            else:
                self._handle_connection_failure()
        except Exception as e:
            self._logger.error(f"Failed to initialize Redis client: {e}")
            self._handle_connection_failure()

    def _test_connection(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.ping()
            return True
        except (RedisConnectionError, RedisError):
            return False

    def _handle_connection_failure(self) -> None:
        self._is_available = False
        if self.config['fallback']:
            self._logger.warning("Redis unavailable, switching to local JSON fallback")
            self._load_fallback_data()
        else:
            self._logger.error("Redis unavailable and fallback disabled")

    def _load_fallback_data(self) -> None:
        if os.path.exists(self.config['fallback_path']):
            try:
                with open(self.config['fallback_path'], 'r', encoding='utf-8') as f:
                    self._fallback_data = json.load(f)
            except json.JSONDecodeError:
                self._fallback_data = {}
                self._logger.warning("Fallback file corrupted, starting fresh")
        else:
            self._fallback_data = {}

    def _save_fallback_data(self) -> None:
        try:
            with open(self.config['fallback_path'], 'w', encoding='utf-8') as f:
                json.dump(self._fallback_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._logger.error(f"Failed to save fallback data: {e}")

    def _execute_with_retry(self, func, *args, **kwargs) -> Any:
        last_exception = None
        for attempt in range(self.config['retry_count']):
            try:
                return func(*args, **kwargs)
            except (RedisConnectionError, RedisError) as e:
                last_exception = e
                self._logger.warning(f"Redis operation failed (attempt {attempt + 1}/{self.config['retry_count']}): {e}")
                self._is_available = False

        if self.config['fallback']:
            self._logger.info("Switching to fallback storage")
            return self._execute_fallback(func.__name__, *args, **kwargs)
        raise last_exception

    def _execute_fallback(self, method: str, *args, **kwargs) -> Any:
        with self._lock:
            result = None
            if method == 'get':
                key = args[0] if args else kwargs.get('name')
                result = self._fallback_data.get(key, None)
            elif method == 'set':
                key = args[0] if len(args) > 0 else kwargs.get('name')
                value = args[1] if len(args) > 1 else kwargs.get('value')
                self._fallback_data[key] = value
                self._save_fallback_data()
                result = True
            elif method == 'hget':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                key = args[1] if len(args) > 1 else kwargs.get('key')
                hash_data = self._fallback_data.get(name, {})
                result = hash_data.get(key, None)
            elif method == 'hset':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                key = args[1] if len(args) > 1 else kwargs.get('key')
                value = args[2] if len(args) > 2 else kwargs.get('value')
                if name not in self._fallback_data:
                    self._fallback_data[name] = {}
                self._fallback_data[name][key] = value
                self._save_fallback_data()
                result = 1
            elif method == 'lpush':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                values = args[1:] if len(args) > 1 else kwargs.get('values', [])
                if name not in self._fallback_data:
                    self._fallback_data[name] = []
                for v in values:
                    self._fallback_data[name].insert(0, v)
                self._save_fallback_data()
                result = len(self._fallback_data[name])
            elif method == 'rpop':
                name = args[0] if args else kwargs.get('name')
                if name in self._fallback_data and self._fallback_data[name]:
                    result = self._fallback_data[name].pop()
                    self._save_fallback_data()
                else:
                    result = None
            elif method == 'zadd':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                mapping = args[1] if len(args) > 1 else kwargs.get('mapping', {})
                if name not in self._fallback_data:
                    self._fallback_data[name] = []
                for member, score in mapping.items():
                    found = False
                    for item in self._fallback_data[name]:
                        if item['member'] == member:
                            item['score'] = score
                            found = True
                            break
                    if not found:
                        self._fallback_data[name].append({'member': member, 'score': score})
                    self._fallback_data[name].sort(key=lambda x: x['score'])
                self._save_fallback_data()
                result = len(mapping)
            elif method == 'zrange':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                start = args[1] if len(args) > 1 else kwargs.get('start', 0)
                end = args[2] if len(args) > 2 else kwargs.get('end', -1)
                withscores = args[3] if len(args) > 3 else kwargs.get('withscores', False)
                data = self._fallback_data.get(name, [])
                if end < 0:
                    end = len(data) + end
                sliced = data[start:end + 1]
                if withscores:
                    result = [(item['member'], item['score']) for item in sliced]
                else:
                    result = [item['member'] for item in sliced]
            elif method == 'delete':
                names = args if args else kwargs.get('names', [])
                count = 0
                for name in names:
                    if name in self._fallback_data:
                        del self._fallback_data[name]
                        count += 1
                self._save_fallback_data()
                result = count
            elif method == 'keys':
                pattern = args[0] if args else kwargs.get('pattern', '*')
                if pattern == '*':
                    result = list(self._fallback_data.keys())
                else:
                    import fnmatch
                    result = [key for key in self._fallback_data.keys() if fnmatch.fnmatch(key, pattern)]
            elif method == 'llen':
                name = args[0] if args else kwargs.get('name')
                result = len(self._fallback_data.get(name, []))
            elif method == 'ltrim':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                start = args[1] if len(args) > 1 else kwargs.get('start', 0)
                end = args[2] if len(args) > 2 else kwargs.get('end', -1)
                if name in self._fallback_data and isinstance(self._fallback_data[name], list):
                    data = self._fallback_data[name]
                    if end < 0:
                        end = len(data) + end
                    self._fallback_data[name] = data[start:end + 1]
                    self._save_fallback_data()
                result = True
            elif method == 'lrange':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                start = args[1] if len(args) > 1 else kwargs.get('start', 0)
                end = args[2] if len(args) > 2 else kwargs.get('end', -1)
                data = self._fallback_data.get(name, [])
                if end < 0:
                    end = len(data) + end
                result = data[start:end + 1]
            elif method == 'lindex':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                index = args[1] if len(args) > 1 else kwargs.get('index', 0)
                data = self._fallback_data.get(name, [])
                if 0 <= index < len(data):
                    result = data[index]
                else:
                    result = None
            elif method == 'lset':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                index = args[1] if len(args) > 1 else kwargs.get('index', 0)
                value = args[2] if len(args) > 2 else kwargs.get('value')
                if name in self._fallback_data and isinstance(self._fallback_data[name], list):
                    data = self._fallback_data[name]
                    if 0 <= index < len(data):
                        data[index] = value
                        self._save_fallback_data()
                        result = True
                    else:
                        result = False
                else:
                    result = False
            elif method == 'lrem':
                name = args[0] if len(args) > 0 else kwargs.get('name')
                count = args[1] if len(args) > 1 else kwargs.get('count', 0)
                value = args[2] if len(args) > 2 else kwargs.get('value')
                if name in self._fallback_data and isinstance(self._fallback_data[name], list):
                    data = self._fallback_data[name]
                    if count == 0:
                        original_len = len(data)
                        self._fallback_data[name] = [v for v in data if v != value]
                        result = original_len - len(self._fallback_data[name])
                    elif count > 0:
                        removed = 0
                        i = 0
                        while i < len(data) and removed < count:
                            if data[i] == value:
                                data.pop(i)
                                removed += 1
                            else:
                                i += 1
                        self._fallback_data[name] = data
                        result = removed
                    else:
                        removed = 0
                        i = len(data) - 1
                        while i >= 0 and removed < abs(count):
                            if data[i] == value:
                                data.pop(i)
                                removed += 1
                            i -= 1
                        self._fallback_data[name] = data
                        result = removed
                    self._save_fallback_data()
                else:
                    result = 0
            elif method == 'hgetall':
                name = args[0] if args else kwargs.get('name')
                result = self._fallback_data.get(name, {})
            return result

    def is_available(self) -> bool:
        """
        检测 Redis 连接状态

        Returns:
            bool: Redis 是否可用
        """
        if not self._is_available and self._client and REDIS_AVAILABLE:
            try:
                self._client.ping()
                self._is_available = True
                self._logger.info("Redis connection restored")
            except (RedisConnectionError, RedisError):
                self._is_available = False
        return self._is_available

    def get(self, name: str) -> Optional[Any]:
        """
        获取指定键的值

        Args:
            name: 键名

        Returns:
            Optional[Any]: 键对应的值，如果不存在返回 None
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('get', name=name)

        def _get():
            value = self._client.get(name)
            if value is not None:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None

        return self._execute_with_retry(_get)

    def set(self, name: str, value: Any, ex: Optional[int] = None, px: Optional[int] = None) -> bool:
        """
        设置指定键的值

        Args:
            name: 键名
            value: 键值
            ex: 过期时间（秒）
            px: 过期时间（毫秒）

        Returns:
            bool: 设置是否成功
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('set', name=name, value=value)

        def _set():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else value
            return self._client.set(name, serialized, ex=ex, px=px)

        return self._execute_with_retry(_set)

    def hget(self, name: str, key: str) -> Optional[Any]:
        """
        获取哈希表中指定字段的值

        Args:
            name: 哈希表名称
            key: 字段名

        Returns:
            Optional[Any]: 字段对应的值，如果不存在返回 None
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('hget', name=name, key=key)

        def _hget():
            value = self._client.hget(name, key)
            if value is not None:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None

        return self._execute_with_retry(_hget)

    def hset(self, name: str, key: str, value: Any) -> int:
        """
        设置哈希表中指定字段的值

        Args:
            name: 哈希表名称
            key: 字段名
            value: 字段值

        Returns:
            int: 设置的字段数量
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('hset', name=name, key=key, value=value)

        def _hset():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else value
            return self._client.hset(name, key, serialized)

        return self._execute_with_retry(_hset)

    def lpush(self, name: str, *values: Any) -> int:
        """
        将一个或多个值插入到列表头部

        Args:
            name: 列表名称
            *values: 要插入的值

        Returns:
            int: 插入后列表的长度
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('lpush', name=name, values=values)

        def _lpush():
            serialized = []
            for v in values:
                serialized.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
            return self._client.lpush(name, *serialized)

        return self._execute_with_retry(_lpush)

    def llen(self, name: str) -> int:
        """
        获取列表的长度

        Args:
            name: 列表名称

        Returns:
            int: 列表的长度
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('llen', name=name)

        return self._execute_with_retry(self._client.llen, name)

    def ltrim(self, name: str, start: int, end: int) -> bool:
        """
        修剪列表，只保留指定范围内的元素

        Args:
            name: 列表名称
            start: 起始索引
            end: 结束索引

        Returns:
            bool: 修剪是否成功
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('ltrim', name=name, start=start, end=end)

        def _ltrim():
            result = self._client.ltrim(name, start, end)
            return result is not None

        return self._execute_with_retry(_ltrim)

    def lrange(self, name: str, start: int = 0, end: int = -1) -> List[Any]:
        """
        获取列表指定范围内的元素

        Args:
            name: 列表名称
            start: 起始索引（默认0）
            end: 结束索引（默认-1，表示最后一个元素）

        Returns:
            List[Any]: 元素列表
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('lrange', name=name, start=start, end=end)

        def _lrange():
            values = self._client.lrange(name, start, end)
            result = []
            for v in values:
                if isinstance(v, bytes):
                    v = v.decode('utf-8')
                try:
                    result.append(json.loads(v))
                except json.JSONDecodeError:
                    result.append(v)
            return result

        return self._execute_with_retry(_lrange)

    def lindex(self, name: str, index: int) -> Optional[Any]:
        """
        获取列表指定索引位置的元素

        Args:
            name: 列表名称
            index: 索引位置

        Returns:
            Optional[Any]: 指定位置的元素，如果不存在返回 None
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('lindex', name=name, index=index)

        def _lindex():
            value = self._client.lindex(name, index)
            if value is not None:
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None

        return self._execute_with_retry(_lindex)

    def lset(self, name: str, index: int, value: Any) -> bool:
        """
        设置列表指定索引位置的元素

        Args:
            name: 列表名称
            index: 索引位置
            value: 元素值

        Returns:
            bool: 设置是否成功
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('lset', name=name, index=index, value=value)

        def _lset():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else value
            result = self._client.lset(name, index, serialized)
            return result is not None

        return self._execute_with_retry(_lset)

    def lrem(self, name: str, count: int, value: Any) -> int:
        """
        从列表中移除指定数量的指定值

        Args:
            name: 列表名称
            count: 移除数量（0表示移除所有匹配项）
            value: 要移除的值

        Returns:
            int: 移除的元素数量
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('lrem', name=name, count=count, value=value)

        def _lrem():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else value
            return self._client.lrem(name, count, serialized)

        return self._execute_with_retry(_lrem)

    def hgetall(self, name: str) -> Dict[str, Any]:
        """
        获取哈希表中所有字段和值

        Args:
            name: 哈希表名称

        Returns:
            Dict[str, Any]: 字段到值的映射字典
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('hgetall', name=name)

        def _hgetall():
            raw_data = self._client.hgetall(name)
            result = {}
            for k, v in raw_data.items():
                if isinstance(k, bytes):
                    k = k.decode('utf-8')
                if isinstance(v, bytes):
                    v = v.decode('utf-8')
                try:
                    result[k] = json.loads(v)
                except json.JSONDecodeError:
                    result[k] = v
            return result

        return self._execute_with_retry(_hgetall)

    def rpop(self, name: str) -> Optional[Any]:
        """
        移除并返回列表的最后一个元素

        Args:
            name: 列表名称

        Returns:
            Optional[Any]: 列表的最后一个元素，如果列表为空返回 None
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('rpop', name=name)

        def _rpop():
            value = self._client.rpop(name)
            if value is not None:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None

        return self._execute_with_retry(_rpop)

    def zadd(self, name: str, mapping: Dict[str, float]) -> int:
        """
        向有序集合添加一个或多个成员，或更新已存在成员的分数

        Args:
            name: 有序集合名称
            mapping: 成员到分数的映射字典

        Returns:
            int: 添加的新成员数量
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('zadd', name=name, mapping=mapping)

        return self._execute_with_retry(self._client.zadd, name, mapping)

    def zrange(self, name: str, start: int = 0, end: int = -1, withscores: bool = False) -> List[Union[str, Tuple[str, float]]]:
        """
        返回有序集合中指定区间内的成员

        Args:
            name: 有序集合名称
            start: 起始索引（默认0）
            end: 结束索引（默认-1，表示最后一个元素）
            withscores: 是否同时返回分数（默认False）

        Returns:
            List[Union[str, Tuple[str, float]]]: 成员列表或(成员,分数)元组列表
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('zrange', name=name, start=start, end=end, withscores=withscores)

        return self._execute_with_retry(self._client.zrange, name, start, end, withscores=withscores)

    def delete(self, *names: str) -> int:
        """
        删除指定的一个或多个键

        Args:
            *names: 要删除的键名

        Returns:
            int: 删除的键数量
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('delete', names=names)

        return self._execute_with_retry(self._client.delete, *names)

    def keys(self, pattern: str = '*') -> List[str]:
        """
        查找所有符合给定模式的键

        Args:
            pattern: 键名匹配模式（默认 '*'）

        Returns:
            List[str]: 符合模式的键名列表
        """
        if not REDIS_AVAILABLE or not self._client:
            return self._execute_fallback('keys', pattern=pattern)

        def _keys():
            return [key.decode('utf-8') if isinstance(key, bytes) else key for key in self._client.keys(pattern)]

        return self._execute_with_retry(_keys)

    def close(self) -> None:
        """
        关闭 Redis 连接
        """
        if self._client:
            try:
                self._client.close()
                self._logger.info("Redis connection closed")
            except Exception as e:
                self._logger.error(f"Error closing Redis connection: {e}")
            self._client = None
            self._is_available = False

    def __del__(self) -> None:
        """
        对象销毁时关闭连接
        """
        self.close()
