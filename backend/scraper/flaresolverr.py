"""
FlareSolverr Integration - Local Cloudflare/Bot Detection Bypass

FlareSolverr is a Docker-based proxy that solves Cloudflare JS challenges
using real browser sessions - no external paid services needed.

Setup:
    docker run -d \
        --name=flaresolverr \
        -p 8191:8191 \
        -e LOG_LEVEL=info \
        ghcr.io/flaresolverr/flaresolverr:latest

Usage:
    solver = FlareSolverr()
    response = await solver.get("https://protected-site.com")
    html = response["solution"]["response"]
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json

from loguru import logger

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@dataclass
class FlareSolverrConfig:
    """FlareSolverr configuration"""
    host: str = "http://localhost:8191"
    max_timeout: int = 60000  # 60 seconds
    session_ttl: int = 900000  # 15 minutes
    

class FlareSolverr:
    """
    Client for FlareSolverr proxy service.
    
    FlareSolverr handles:
    - Cloudflare JS challenges
    - Cloudflare CAPTCHAs (hCaptcha)
    - DDoS-GUARD
    - Other JS-based protections
    
    It runs a real browser session and returns the solved page content.
    """
    
    def __init__(self, config: Optional[FlareSolverrConfig] = None):
        if not HAS_HTTPX:
            raise RuntimeError("httpx not installed. Run: pip install httpx")
        
        self.config = config or FlareSolverrConfig()
        self._sessions: Dict[str, str] = {}  # program -> session_id
    
    @property
    def endpoint(self) -> str:
        return f"{self.config.host}/v1"
    
    async def is_available(self) -> bool:
        """Check if FlareSolverr is running"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.config.host)
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"FlareSolverr not available: {e}")
            return False
    
    async def get_session(self, program: str) -> Optional[str]:
        """Get or create a session for a program"""
        if program in self._sessions:
            return self._sessions[program]
        
        try:
            session_id = await self._create_session()
            if session_id:
                self._sessions[program] = session_id
            return session_id
        except Exception as e:
            logger.error(f"Failed to create FlareSolverr session: {e}")
            return None
    
    async def _create_session(self) -> Optional[str]:
        """Create a new browser session"""
        payload = {
            "cmd": "sessions.create",
            "session_ttl_minutes": self.config.session_ttl // 60000
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.endpoint, json=payload)
                data = response.json()
                
                if data.get("status") == "ok":
                    session_id = data.get("session")
                    logger.info(f"Created FlareSolverr session: {session_id}")
                    return session_id
                else:
                    logger.error(f"Failed to create session: {data}")
                    return None
        except Exception as e:
            logger.error(f"FlareSolverr session creation error: {e}")
            return None
    
    async def destroy_session(self, session_id: str) -> bool:
        """Destroy a browser session"""
        payload = {
            "cmd": "sessions.destroy",
            "session": session_id
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.endpoint, json=payload)
                data = response.json()
                
                # Remove from cache
                for program, sid in list(self._sessions.items()):
                    if sid == session_id:
                        del self._sessions[program]
                
                return data.get("status") == "ok"
        except Exception as e:
            logger.warning(f"Failed to destroy session: {e}")
            return False
    
    async def get(
        self,
        url: str,
        session_id: Optional[str] = None,
        max_timeout: Optional[int] = None,
        cookies: Optional[List[Dict]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch a URL using FlareSolverr.
        
        Args:
            url: URL to fetch
            session_id: Optional session ID for persistent browser
            max_timeout: Request timeout in ms
            cookies: Optional cookies to send
            headers: Optional headers
            
        Returns:
            FlareSolverr response with solution containing HTML
        """
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": max_timeout or self.config.max_timeout
        }
        
        if session_id:
            payload["session"] = session_id
        
        if cookies:
            payload["cookies"] = cookies
        
        if headers:
            payload["headers"] = headers
        
        logger.info(f"FlareSolverr GET: {url}")
        
        try:
            timeout = (max_timeout or self.config.max_timeout) / 1000 + 10
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.endpoint, json=payload)
                data = response.json()
                
                if data.get("status") == "ok":
                    solution = data.get("solution", {})
                    logger.info(f"FlareSolverr solved: status={solution.get('status')}")
                    return data
                else:
                    logger.error(f"FlareSolverr failed: {data.get('message')}")
                    return data
                    
        except httpx.TimeoutException:
            logger.error(f"FlareSolverr timeout for {url}")
            return {"status": "error", "message": "timeout"}
        except Exception as e:
            logger.error(f"FlareSolverr error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def post(
        self,
        url: str,
        post_data: str,
        session_id: Optional[str] = None,
        max_timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        POST request using FlareSolverr.
        
        Args:
            url: URL to post to
            post_data: URL-encoded form data
            session_id: Optional session ID
            max_timeout: Request timeout in ms
            
        Returns:
            FlareSolverr response
        """
        payload = {
            "cmd": "request.post",
            "url": url,
            "postData": post_data,
            "maxTimeout": max_timeout or self.config.max_timeout
        }
        
        if session_id:
            payload["session"] = session_id
        
        logger.info(f"FlareSolverr POST: {url}")
        
        try:
            timeout = (max_timeout or self.config.max_timeout) / 1000 + 10
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.endpoint, json=payload)
                return response.json()
        except Exception as e:
            logger.error(f"FlareSolverr POST error: {e}")
            return {"status": "error", "message": str(e)}
    
    def extract_html(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract HTML from FlareSolverr response"""
        if response.get("status") != "ok":
            return None
        
        solution = response.get("solution", {})
        return solution.get("response")
    
    def extract_cookies(self, response: Dict[str, Any]) -> List[Dict]:
        """Extract cookies from FlareSolverr response"""
        if response.get("status") != "ok":
            return []
        
        solution = response.get("solution", {})
        return solution.get("cookies", [])
    
    def extract_user_agent(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract user agent from FlareSolverr response"""
        if response.get("status") != "ok":
            return None
        
        solution = response.get("solution", {})
        return solution.get("userAgent")


class FlareSolverrScraper:
    """
    Scraper that uses FlareSolverr for protected sites.
    
    Combines FlareSolverr for initial challenge bypass
    with direct requests for subsequent pages.
    """
    
    def __init__(self, program: str):
        self.program = program
        self.solver = FlareSolverr()
        self._cookies: List[Dict] = []
        self._user_agent: Optional[str] = None
        self._session_id: Optional[str] = None
    
    async def initialize(self) -> bool:
        """Initialize FlareSolverr session"""
        if not await self.solver.is_available():
            logger.warning("FlareSolverr not available - run Docker container first")
            return False
        
        self._session_id = await self.solver.get_session(self.program)
        return self._session_id is not None
    
    async def get_page(self, url: str) -> Optional[str]:
        """
        Get page content, bypassing Cloudflare if needed.
        
        Returns:
            HTML content or None if failed
        """
        response = await self.solver.get(
            url,
            session_id=self._session_id,
            cookies=self._cookies if self._cookies else None
        )
        
        html = self.solver.extract_html(response)
        
        if html:
            # Update cookies for subsequent requests
            self._cookies = self.solver.extract_cookies(response)
            self._user_agent = self.solver.extract_user_agent(response)
        
        return html
    
    async def close(self):
        """Cleanup session"""
        if self._session_id:
            await self.solver.destroy_session(self._session_id)


# ============== Convenience Functions ==============

async def fetch_with_flaresolverr(url: str) -> Optional[str]:
    """
    One-shot fetch using FlareSolverr.
    
    Usage:
        html = await fetch_with_flaresolverr("https://protected-site.com")
    """
    solver = FlareSolverr()
    
    if not await solver.is_available():
        logger.error("FlareSolverr not running. Start with: docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")
        return None
    
    response = await solver.get(url)
    return solver.extract_html(response)


def get_flaresolverr_docker_command() -> str:
    """Get the Docker command to start FlareSolverr"""
    return """docker run -d \\
    --name=flaresolverr \\
    -p 8191:8191 \\
    -e LOG_LEVEL=info \\
    --restart unless-stopped \\
    ghcr.io/flaresolverr/flaresolverr:latest"""
