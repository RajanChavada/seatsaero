#!/usr/bin/env python3
"""
Seats Aero Clone - Application Entry Point
"""
import sys
import os

# Add backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from loguru import logger

from config.settings import settings


def setup_logging():
    """Configure logging"""
    logger.remove()  # Remove default handler
    
    # Console handler
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # File handler (if configured)
    if settings.log_file:
        os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
        logger.add(
            settings.log_file,
            level=settings.log_level,
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )


def main():
    """Run the application"""
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("Seats Aero Clone - Award Flight Search")
    logger.info("=" * 50)
    
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,  # Enable for development
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
