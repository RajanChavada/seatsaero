"""
Proxy Rotator - Manages proxy rotation for avoiding IP-based rate limiting
"""
import random
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import httpx
from loguru import logger

from config import settings


class ProxyProtocol(str, Enum):
    """Supported proxy protocols"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


@dataclass
class Proxy:
    """Represents a proxy server"""
    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: Optional[str] = None
    password: Optional[str] = None
    
    # Health tracking
    is_working: bool = True
    last_used: Optional[datetime] = None
    fail_count: int = 0
    success_count: int = 0
    avg_response_time: float = 0.0
    
    @property
    def url(self) -> str:
        """Get proxy URL string"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to proxy dict for requests/httpx"""
        url = self.url
        return {
            "http://": url,
            "https://": url,
        }
    
    def mark_success(self, response_time: float) -> None:
        """Mark proxy as successful"""
        self.success_count += 1
        self.fail_count = 0
        self.is_working = True
        self.last_used = datetime.utcnow()
        # Rolling average
        self.avg_response_time = (
            (self.avg_response_time * (self.success_count - 1) + response_time) 
            / self.success_count
        )
    
    def mark_failure(self) -> None:
        """Mark proxy as failed"""
        self.fail_count += 1
        self.last_used = datetime.utcnow()
        if self.fail_count >= 3:
            self.is_working = False


class RotationStrategy(str, Enum):
    """Proxy rotation strategies"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_USED = "least_used"
    FASTEST = "fastest"


class ProxyRotator:
    """
    Manages a pool of proxies with rotation and health checking.
    """
    
    # Free proxy list sources (for MVP)
    FREE_PROXY_SOURCES = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    ]
    
    def __init__(
        self,
        proxies: Optional[List[Proxy]] = None,
        strategy: RotationStrategy = RotationStrategy.RANDOM
    ):
        self._proxies: List[Proxy] = proxies or []
        self._strategy = strategy
        self._current_index = 0
        self._lock = asyncio.Lock()
    
    @property
    def working_proxies(self) -> List[Proxy]:
        """Get list of working proxies"""
        return [p for p in self._proxies if p.is_working]
    
    @property
    def proxy_count(self) -> int:
        """Total number of proxies"""
        return len(self._proxies)
    
    @property
    def working_count(self) -> int:
        """Number of working proxies"""
        return len(self.working_proxies)
    
    def add_proxy(self, proxy: Proxy) -> None:
        """Add a proxy to the pool"""
        self._proxies.append(proxy)
    
    def add_from_string(self, proxy_string: str) -> None:
        """
        Add proxy from string format: host:port or protocol://host:port
        """
        try:
            if "://" in proxy_string:
                protocol, rest = proxy_string.split("://")
                host, port = rest.split(":")
                protocol = ProxyProtocol(protocol)
            else:
                host, port = proxy_string.split(":")
                protocol = ProxyProtocol.HTTP
            
            self.add_proxy(Proxy(
                host=host.strip(),
                port=int(port.strip()),
                protocol=protocol
            ))
        except Exception as e:
            logger.warning(f"Failed to parse proxy string '{proxy_string}': {e}")
    
    def get_next(self) -> Optional[Dict[str, str]]:
        """
        Get next proxy based on rotation strategy.
        Returns proxy dict or None if no working proxies.
        """
        working = self.working_proxies
        if not working:
            logger.warning("No working proxies available")
            return None
        
        proxy: Optional[Proxy] = None
        
        if self._strategy == RotationStrategy.RANDOM:
            proxy = random.choice(working)
            
        elif self._strategy == RotationStrategy.ROUND_ROBIN:
            self._current_index = self._current_index % len(working)
            proxy = working[self._current_index]
            self._current_index += 1
            
        elif self._strategy == RotationStrategy.LEAST_USED:
            proxy = min(working, key=lambda p: p.success_count + p.fail_count)
            
        elif self._strategy == RotationStrategy.FASTEST:
            # Filter proxies with usage data
            used_proxies = [p for p in working if p.success_count > 0]
            if used_proxies:
                proxy = min(used_proxies, key=lambda p: p.avg_response_time)
            else:
                proxy = random.choice(working)
        
        if proxy:
            logger.debug(f"Using proxy: {proxy.host}:{proxy.port}")
            return proxy.to_dict()
        
        return None
    
    async def fetch_free_proxies(self) -> int:
        """
        Fetch proxies from free proxy lists.
        Returns number of proxies added.
        """
        added = 0
        
        async with httpx.AsyncClient(timeout=10) as client:
            for source_url in self.FREE_PROXY_SOURCES:
                try:
                    response = await client.get(source_url)
                    if response.status_code == 200:
                        lines = response.text.strip().split("\n")
                        for line in lines:
                            line = line.strip()
                            if line and ":" in line:
                                self.add_from_string(line)
                                added += 1
                        logger.info(f"Fetched proxies from {source_url}")
                except Exception as e:
                    logger.warning(f"Failed to fetch proxies from {source_url}: {e}")
        
        logger.info(f"Added {added} proxies from free sources")
        return added
    
    async def validate_proxy(self, proxy: Proxy, test_url: str = "https://httpbin.org/ip") -> bool:
        """
        Test if a proxy is working.
        """
        try:
            start_time = datetime.utcnow()
            
            async with httpx.AsyncClient(
                proxies=proxy.to_dict(),
                timeout=10
            ) as client:
                response = await client.get(test_url)
                
                if response.status_code == 200:
                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    proxy.mark_success(elapsed)
                    return True
                else:
                    proxy.mark_failure()
                    return False
                    
        except Exception as e:
            proxy.mark_failure()
            logger.debug(f"Proxy {proxy.host}:{proxy.port} failed: {e}")
            return False
    
    async def validate_all(self, concurrency: int = 10) -> int:
        """
        Validate all proxies concurrently.
        Returns number of working proxies.
        """
        logger.info(f"Validating {len(self._proxies)} proxies...")
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def validate_with_limit(proxy: Proxy):
            async with semaphore:
                return await self.validate_proxy(proxy)
        
        tasks = [validate_with_limit(p) for p in self._proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        working = sum(1 for r in results if r is True)
        logger.info(f"Proxy validation complete: {working}/{len(self._proxies)} working")
        
        return working
    
    def remove_dead_proxies(self) -> int:
        """Remove non-working proxies from pool"""
        initial_count = len(self._proxies)
        self._proxies = [p for p in self._proxies if p.is_working]
        removed = initial_count - len(self._proxies)
        logger.info(f"Removed {removed} dead proxies")
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get proxy pool statistics"""
        return {
            "total": self.proxy_count,
            "working": self.working_count,
            "dead": self.proxy_count - self.working_count,
            "strategy": self._strategy.value,
        }
