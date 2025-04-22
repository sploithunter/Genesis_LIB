#!/usr/bin/env python3
import logging, asyncio
from typing import Dict, Any
from pydantic import BaseModel, Field

from genesis_lib.decorators import genesis_function
from genesis_lib.enhanced_service_base import EnhancedServiceBase

# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #
class BinaryArgs(BaseModel):
    x: float = Field(..., ge=-1_000_000, le=1_000_000, description="First number")
    y: float = Field(..., ge=-1_000_000, le=1_000_000, description="Second number")

# --------------------------------------------------------------------------- #
# Service                                                                     #
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("calculator_service")

class CalculatorService(EnhancedServiceBase):
    """Implementation of the calculator service using the decorator pattern."""

    def __init__(self):
        super().__init__("CalculatorService", capabilities=["calculator", "math"])
        logger.info("CalculatorService initialized")
        # Everything is now auto‑registered; just advertise.
        self._advertise_functions()
        logger.info("Functions advertised")

    # ------------------------------------------------------------------ #
    # Decorated functions                                                #
    # ------------------------------------------------------------------ #
    @genesis_function(description="Add two numbers",
                      model=BinaryArgs,
                      operation_type="calculation")
    async def add(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Add two numbers."""
        logger.info(f"Received add request: x={x}, y={y}")
        self.publish_function_call_event("add", {"x": x, "y": y}, request_info)
        result = x + y
        self.publish_function_result_event("add", {"result": result}, request_info)
        logger.info(f"Add result: {result}")
        return self.format_response({"x": x, "y": y}, result)

    @genesis_function(description="Subtract two numbers",
                      model=BinaryArgs,
                      operation_type="calculation")
    async def subtract(self, x: float, y: float, request_info=None):
        logger.info(f"Received subtract request: x={x}, y={y}")
        self.publish_function_call_event("subtract", {"x": x, "y": y}, request_info)
        result = x - y
        self.publish_function_result_event("subtract", {"result": result}, request_info)
        logger.info(f"Subtract result: {result}")
        return self.format_response({"x": x, "y": y}, result)

    @genesis_function(description="Multiply two numbers",
                      model=BinaryArgs,
                      operation_type="calculation")
    async def multiply(self, x: float, y: float, request_info=None):
        logger.info(f"Received multiply request: x={x}, y={y}")
        self.publish_function_call_event("multiply", {"x": x, "y": y}, request_info)
        result = x * y
        self.publish_function_result_event("multiply", {"result": result}, request_info)
        logger.info(f"Multiply result: {result}")
        return self.format_response({"x": x, "y": y}, result)

    @genesis_function(description="Divide two numbers",
                      model=BinaryArgs,
                      operation_type="calculation")
    async def divide(self, x: float, y: float, request_info=None):
        logger.info(f"Received divide request: x={x}, y={y}")
        self.publish_function_call_event("divide", {"x": x, "y": y}, request_info)
        if y == 0:
            raise ValueError("Cannot divide by zero")
        result = x / y
        self.publish_function_result_event("divide", {"result": result}, request_info)
        logger.info(f"Divide result: {result}")
        return self.format_response({"x": x, "y": y}, result)

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
