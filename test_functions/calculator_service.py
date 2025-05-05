#!/usr/bin/env python3
import logging, asyncio, sys
from typing import Dict, Any
from datetime import datetime
from genesis_lib.decorators import genesis_function
from genesis_lib.enhanced_service_base import EnhancedServiceBase

# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #
class CalculatorError(Exception):
    """Base exception for calculator service errors."""
    pass

class InvalidInputError(CalculatorError):
    """Raised when input values are invalid."""
    pass

class DivisionByZeroError(CalculatorError):
    """Raised when attempting to divide by zero."""
    pass

# --------------------------------------------------------------------------- #
# Service                                                                     #
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    force=True)  # Force reconfiguration of the root logger
logger = logging.getLogger("calculator_service")
logger.setLevel(logging.DEBUG)  # Explicitly set logger level

class CalculatorService(EnhancedServiceBase):
    """Implementation of the calculator service using the decorator pattern.
    
    This service provides basic arithmetic operations with input validation
    and standardized response formatting. It extends EnhancedServiceBase to
    leverage built-in function registration, monitoring, and discovery.
    """

    def __init__(self):
        logger.info("===== DDS TRACE: CalculatorService initializing... =====")
        super().__init__("CalculatorService", capabilities=["calculator", "math"])
        logger.info("===== DDS TRACE: CalculatorService EnhancedServiceBase initialized. =====")
        logger.info("===== DDS TRACE: Calling _advertise_functions... =====")
        self._advertise_functions()
        logger.info("===== DDS TRACE: _advertise_functions called. =====")
        logger.info("CalculatorService initialized")

    @genesis_function()
    async def add(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Add two numbers together.
        
        Args:
            x: First number to add (example: 5.0)
            y: Second number to add (example: 3.0)
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the addition
            
        Examples:
            >>> await add(5, 3)
            {'result': 8}
            
        Raises:
            InvalidInputError: If either number is outside the valid range [-1,000,000, 1,000,000]
        """
        logger.info(f"Received add request: x={x}, y={y}")
        self.publish_function_call_event("add", {"x": x, "y": y}, request_info)
        
        try:
            result = x + y
            self.publish_function_result_event("add", {"result": result}, request_info)
            logger.info(f"Add result: {result}")
            return {"result": result}
        except Exception as e:
            logger.error(f"Error in add operation: {str(e)}")
            raise InvalidInputError(f"Failed to add numbers: {str(e)}")

    @genesis_function()
    async def subtract(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Subtract the second number from the first.
        
        Args:
            x: The number to subtract from (example: 5.0)
            y: The number to subtract (example: 3.0)
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the subtraction
            
        Examples:
            >>> await subtract(5, 3)
            {'result': 2}
            
        Raises:
            InvalidInputError: If either number is outside the valid range [-1,000,000, 1,000,000]
        """
        logger.info(f"Received subtract request: x={x}, y={y}")
        self.publish_function_call_event("subtract", {"x": x, "y": y}, request_info)
        
        try:
            result = x - y
            self.publish_function_result_event("subtract", {"result": result}, request_info)
            logger.info(f"Subtract result: {result}")
            return {"result": result}
        except Exception as e:
            logger.error(f"Error in subtract operation: {str(e)}")
            raise InvalidInputError(f"Failed to subtract numbers: {str(e)}")

    @genesis_function()
    async def multiply(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Multiply two numbers together.
        
        Args:
            x: First number to multiply (example: 5.0)
            y: Second number to multiply (example: 3.0)
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the multiplication
            
        Examples:
            >>> await multiply(5, 3)
            {'result': 15}
            
        Raises:
            InvalidInputError: If either number is outside the valid range [-1,000,000, 1,000,000]
        """
        logger.info(f"Received multiply request: x={x}, y={y}")
        self.publish_function_call_event("multiply", {"x": x, "y": y}, request_info)
        
        try:
            result = x * y
            self.publish_function_result_event("multiply", {"result": result}, request_info)
            logger.info(f"Multiply result: {result}")
            return {"result": result}
        except Exception as e:
            logger.error(f"Error in multiply operation: {str(e)}")
            raise InvalidInputError(f"Failed to multiply numbers: {str(e)}")

    @genesis_function()
    async def divide(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Divide the first number by the second.
        
        Args:
            x: The number to divide (example: 6.0)
            y: The number to divide by (example: 2.0)
            request_info: Optional request metadata
            
        Returns:
            Dict containing the result of the division
            
        Examples:
            >>> await divide(6, 2)
            {'result': 3}
            
        Raises:
            InvalidInputError: If either number is outside the valid range [-1,000,000, 1,000,000]
            DivisionByZeroError: If attempting to divide by zero
        """
        logger.info(f"Received divide request: x={x}, y={y}")
        self.publish_function_call_event("divide", {"x": x, "y": y}, request_info)
        
        try:
            if y == 0:
                raise DivisionByZeroError("Cannot divide by zero")
            result = x / y
            self.publish_function_result_event("divide", {"result": result}, request_info)
            logger.info(f"Divide result: {result}")
            return {"result": result}
        except DivisionByZeroError:
            logger.error("Attempted division by zero")
            raise
        except Exception as e:
            logger.error(f"Error in divide operation: {str(e)}")
            raise InvalidInputError(f"Failed to divide numbers: {str(e)}")

# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main():
    logger.info("SERVICE: Starting calculator service")
    try:
        service = CalculatorService()
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("SERVICE: Shutting down calculator service")

if __name__ == "__main__":
    main()
