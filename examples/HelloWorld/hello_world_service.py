#!/usr/bin/env python3

"""
A simple calculator service that demonstrates basic Genesis service functionality.
Provides basic arithmetic operations: add and multiply.
"""

import logging
import asyncio
from typing import Dict, Any
from genesis_lib.enhanced_service_base import EnhancedServiceBase
from genesis_lib.decorators import genesis_function

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hello_calculator")

class HelloCalculator(EnhancedServiceBase):
    """A simple calculator service demonstrating Genesis functionality."""
    
    def __init__(self):
        """Initialize the calculator service."""
        super().__init__(
            "HelloCalculator",
            capabilities=["calculator", "math"]
        )
        logger.info("HelloCalculator service initialized")
        self._advertise_functions()
        logger.info("Functions advertised")

    @genesis_function()
    async def add(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Add two numbers together.
        
        Args:
            x: First number to add
            y: Second number to add
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the addition
            
        Examples:
            >>> await add(5, 3)
            {'result': 8}
        """
        logger.info(f"Received add request: x={x}, y={y}")
        
        try:
            result = x + y
            logger.info(f"Add result: {result}")
            return {"result": result}
        except Exception as e:
            logger.error(f"Error in add operation: {str(e)}")
            raise

    @genesis_function()
    async def multiply(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Multiply two numbers together.
        
        Args:
            x: First number to multiply
            y: Second number to multiply
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the multiplication
            
        Examples:
            >>> await multiply(5, 3)
            {'result': 15}
        """
        logger.info(f"Received multiply request: x={x}, y={y}")
        
        try:
            result = x * y
            logger.info(f"Multiply result: {result}")
            return {"result": result}
        except Exception as e:
            logger.error(f"Error in multiply operation: {str(e)}")
            raise

def main():
    """Run the calculator service."""
    logger.info("Starting HelloCalculator service")
    try:
        service = HelloCalculator()
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Shutting down HelloCalculator service")

if __name__ == "__main__":
    main() 