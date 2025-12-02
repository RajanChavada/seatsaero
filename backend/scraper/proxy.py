"""
Proxy Manager - Advanced proxy rotation with sticky sessions and per-program pools
"""
import random
import asyncio
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib

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
class ProxyConfig:
    """Proxy configuration with authentication"""
    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: Optional[str] = None
    password: Optional[str] = None
    
    # Health and usage tracking
    is_working: bool = True
    is_hot: bool = False  # Marked hot after CAPTCHA/block
    hot_until: Optional[datetime] = None
    last_used: Optional[datetime] = None
    fail_count: int = 0
    success_count: int = 0
    captcha_count: int = 0
    avg_response_time: float = 0.0
    
    @property
    def id(self) -> str:
        """Unique identifier for this proxy"""
        return hashlib.md5(f"{self.host}:{self.port}".encode()).hexdigest()[:8]
    
    @property
    def url(self) -> str:
        """Get proxy URL string"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"
    
    @property
    def is_available(self) -> bool:
        """Check if proxy is available for use"""
        if not self.is_working:
            return False
        if self.is_hot:
            if self.hot_until and datetime.utcnow() > self.hot_until:
                self.is_hot = False
                self.hot_until = None
                return True
            return False
        return True
    
    def to_selenium_arg(self) -> str:
        """Get proxy argument for Selenium/Chrome"""
        if self.username and self.password:
            # For authenticated proxies, we need extension or other method
            # For now, return URL that might work with some proxy types
            return f"{self.host}:{self.port}"
        return f"{self.host}:{self.port}"
    
    def to_httpx_proxy(self) -> str:
        """Get proxy URL for httpx"""
        return self.url
    
    def mark_success(self, response_time: float = 0.0) -> None:
        """Mark proxy as successful"""
        self.success_count += 1
        self.fail_count = 0
        self.is_working = True
        self.last_used = datetime.utcnow()
        if response_time > 0:
            # Rolling average
            total = self.success_count
            self.avg_response_time = (
                (self.avg_response_time * (total - 1) + response_time) / total
            )
    
    def mark_failure(self, reason: str = "unknown") -> None:
        """Mark proxy as failed"""
        self.fail_count += 1
        self.last_used = datetime.utcnow()
        logger.warning(f"Proxy {self.id} failed: {reason} (fails: {self.fail_count})")
        if self.fail_count >= 3:
            self.is_working = False
            logger.info(f"Proxy {self.id} marked as not working after {self.fail_count} failures")
    
    def mark_hot(self, duration_mins: int = None) -> None:
        """Mark proxy as hot (temporarily blocked/detected)"""
        duration = duration_mins or settings.proxy_hot_duration_mins
        self.is_hot = True
        self.hot_until = datetime.utcnow() + timedelta(minutes=duration)
        self.captcha_count += 1
        logger.warning(f"Proxy {self.id} marked HOT until {self.hot_until} (CAPTCHAs: {self.captcha_count})")


@dataclass
class StickySession:
    """Represents a sticky proxy session for a job"""
    proxy: ProxyConfig
    program: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    request_count: int = 0
    
    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(
                minutes=settings.proxy_sticky_duration_mins
            )
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
    
    def use(self) -> ProxyConfig:
        """Use this session for a request"""
        self.request_count += 1
        return self.proxy


class ProxyPool:
    """
    Manages proxy pools with per-program support, sticky sessions, and hot-marking.
    
    Features:
    - Per-program proxy pools
    - Sticky sessions (same proxy for duration/job)
    - Hot-marking for blocked/CAPTCHA'd proxies
    - Health tracking and automatic rotation
    """
    
    def __init__(self):
        # Per-program proxy pools
        self._pools: Dict[str, List[ProxyConfig]] = {}
        # Active sticky sessions: job_id -> StickySession
        self._sessions: Dict[str, StickySession] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Initialize pools from settings
        self._init_pools()
    
    def _init_pools(self) -> None:
        """Initialize proxy pools from settings"""
        # Load per-program pools
        for program in ["united", "aeroplan"]:
            pool = settings.get_program_proxy_pool(program)
            auth = settings.get_program_proxy_auth(program)
            
            if pool:
                self._pools[program] = []
                for proxy_url in pool:
                    proxy = self._parse_proxy_url(proxy_url, auth)
                    if proxy:
                        self._pools[program].append(proxy)
                logger.info(f"Loaded {len(self._pools[program])} proxies for {program}")
        
        # Load default pool
        default_pool = settings.get_program_proxy_pool("default")
        if default_pool:
            self._pools["default"] = []
            for proxy_url in default_pool:
                proxy = self._parse_proxy_url(proxy_url)
                if proxy:
                    self._pools["default"].append(proxy)
            logger.info(f"Loaded {len(self._pools['default'])} default proxies")
    
    def _parse_proxy_url(
        self, 
        proxy_str: str, 
        auth: Optional[Dict[str, str]] = None
    ) -> Optional[ProxyConfig]:
        """Parse proxy URL string into ProxyConfig"""
        try:
            # Handle different formats:
            # host:port
            # protocol://host:port
            # protocol://user:pass@host:port
            
            protocol = ProxyProtocol.HTTP
            username = auth.get("username") if auth else None
            password = auth.get("password") if auth else None
            
            if "://" in proxy_str:
                proto_part, rest = proxy_str.split("://", 1)
                protocol = ProxyProtocol(proto_part.lower())
                
                if "@" in rest:
                    auth_part, host_part = rest.rsplit("@", 1)
                    if ":" in auth_part:
                        username, password = auth_part.split(":", 1)
                    host, port = host_part.split(":")
                else:
                    host, port = rest.split(":")
            else:
                host, port = proxy_str.split(":")
            
            return ProxyConfig(
                host=host.strip(),
                port=int(port.strip()),
                protocol=protocol,
                username=username,
                password=password
            )
        except Exception as e:
            logger.warning(f"Failed to parse proxy '{proxy_str}': {e}")
            return None
    
    def add_proxy(self, program: str, proxy: ProxyConfig) -> None:
        """Add a proxy to a program's pool"""
        if program not in self._pools:
            self._pools[program] = []
        self._pools[program].append(proxy)
    
    def add_proxies_from_list(self, program: str, proxy_urls: List[str]) -> int:
        """Add multiple proxies from URL list"""
        added = 0
        for url in proxy_urls:
            proxy = self._parse_proxy_url(url)
            if proxy:
                self.add_proxy(program, proxy)
                added += 1
        return added
    
    def get_pool(self, program: str) -> List[ProxyConfig]:
        """Get proxy pool for a program (falls back to default)"""
        program_lower = program.lower()
        if program_lower in self._pools:
            return self._pools[program_lower]
        return self._pools.get("default", [])
    
    def get_available_proxies(self, program: str) -> List[ProxyConfig]:
        """Get available (non-hot, working) proxies for a program"""
        pool = self.get_pool(program)
        return [p for p in pool if p.is_available]
    
    async def acquire(
        self, 
        program: str, 
        job_id: Optional[str] = None,
        sticky: bool = True
    ) -> Optional[ProxyConfig]:
        """
        Acquire a proxy for a program/job.
        
        Args:
            program: Program name (united, aeroplan, etc.)
            job_id: Optional job ID for sticky sessions
            sticky: Whether to use sticky sessions
            
        Returns:
            ProxyConfig or None if no proxies available
        """
        if not settings.proxy_enabled:
            return None
        
        async with self._lock:
            # Check for existing sticky session
            if sticky and job_id and job_id in self._sessions:
                session = self._sessions[job_id]
                if not session.is_expired and session.proxy.is_available:
                    return session.use()
                else:
                    # Session expired or proxy unavailable
                    del self._sessions[job_id]
            
            # Get available proxies
            available = self.get_available_proxies(program)
            if not available:
                logger.warning(f"No available proxies for {program}")
                return None
            
            # Select proxy (random for now, could add more strategies)
            proxy = random.choice(available)
            
            # Create sticky session if requested
            if sticky and job_id:
                self._sessions[job_id] = StickySession(
                    proxy=proxy,
                    program=program
                )
            
            proxy.last_used = datetime.utcnow()
            return proxy
    
    def release(self, job_id: str) -> None:
        """Release a sticky session"""
        if job_id in self._sessions:
            del self._sessions[job_id]
    
    def mark_hot(self, program: str, proxy_id: str, duration_mins: int = None) -> None:
        """Mark a proxy as hot (blocked/detected)"""
        pool = self.get_pool(program)
        for proxy in pool:
            if proxy.id == proxy_id:
                proxy.mark_hot(duration_mins)
                break
    
    def mark_success(self, program: str, proxy_id: str, response_time: float = 0.0) -> None:
        """Mark a proxy request as successful"""
        pool = self.get_pool(program)
        for proxy in pool:
            if proxy.id == proxy_id:
                proxy.mark_success(response_time)
                break
    
    def mark_failure(self, program: str, proxy_id: str, reason: str = "unknown") -> None:
        """Mark a proxy request as failed"""
        pool = self.get_pool(program)
        for proxy in pool:
            if proxy.id == proxy_id:
                proxy.mark_failure(reason)
                break
    
    def get_stats(self) -> Dict[str, Any]:
        """Get proxy pool statistics"""
        stats = {}
        for program, pool in self._pools.items():
            available = [p for p in pool if p.is_available]
            hot = [p for p in pool if p.is_hot]
            stats[program] = {
                "total": len(pool),
                "available": len(available),
                "hot": len(hot),
                "not_working": len(pool) - len(available) - len(hot),
            }
        stats["active_sessions"] = len(self._sessions)
        return stats
    
    def cleanup_sessions(self) -> int:
        """Clean up expired sticky sessions"""
        expired = [
            job_id for job_id, session in self._sessions.items()
            if session.is_expired
        ]
        for job_id in expired:
            del self._sessions[job_id]
        return len(expired)


# Global proxy pool instance
_proxy_pool: Optional[ProxyPool] = None


def get_proxy_pool() -> ProxyPool:
    """Get or create the global proxy pool"""
    global _proxy_pool
    if _proxy_pool is None:
        _proxy_pool = ProxyPool()
    return _proxy_pool


# ============== Legacy Support ==============
# Keep backward compatibility with old ProxyRotator interface

class ProxyRotator:
    """
    Legacy proxy rotator - wraps ProxyPool for backward compatibility.
    """
    
    def __init__(self):
        self._pool = get_proxy_pool()
        self._program = "default"
    
    def get_next(self) -> Optional[Dict[str, str]]:
        """Get next proxy (non-async legacy method)"""
        available = self._pool.get_available_proxies(self._program)
        if not available:
            return None
        
        proxy = random.choice(available)
        return {
            "http": proxy.url,
            "https": proxy.url,
        }
    
    def mark_success(self, proxy_url: str, response_time: float = 0.0) -> None:
        """Mark proxy as successful"""
        pass  # Handled by ProxyPool
    
    def mark_failure(self, proxy_url: str) -> None:
        """Mark proxy as failed"""
        pass  # Handled by ProxyPool


async def load_free_proxies() -> int:
    """Load free proxies from public sources"""
    FREE_PROXY_SOURCES = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    ]
    
    pool = get_proxy_pool()
    total_added = 0
    
    async with httpx.AsyncClient(timeout=10) as client:
        for source in FREE_PROXY_SOURCES:
            try:
                response = await client.get(source)
                if response.status_code == 200:
                    lines = response.text.strip().split("\n")
                    added = pool.add_proxies_from_list("default", lines[:50])  # Limit to 50 per source
                    total_added += added
                    logger.info(f"Loaded {added} proxies from {source}")
            except Exception as e:
                logger.warning(f"Failed to load proxies from {source}: {e}")
    
    return total_added
