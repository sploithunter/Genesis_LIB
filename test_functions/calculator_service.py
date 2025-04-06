#!/usr/bin/env python3

import logging
import asyncio
import json
from typing import Dict, Any
from genesis_lib.enhanced_service_base import EnhancedServiceBase

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("calculator_service")

class CalculatorService(EnhancedServiceBase):
    """Implementation of the calculator service using Genesis RPC framework"""
    
    def __init__(self):
        """Initialize the calculator service"""
        # Initialize the enhanced base class with service name and capabilities
        super().__init__(
            service_name="CalculatorService",
            capabilities=["calculator", "math"]
        )
        
        # Get common number schema with validation
        number_schema = self.get_common_schema("number")
        number_schema.update({
            "minimum": -1000000,  # Reasonable limits for calculator
            "maximum": 1000000
        })
        
        # Register calculator functions with OpenAI-style schemas
        self.register_enhanced_function(
            self.add,
            "Add two numbers",
            {
                "type": "object",
                "properties": {
                    "x": number_schema.copy(),
                    "y": number_schema.copy()
                },
                "required": ["x", "y"],
                "additionalProperties": False
            },
            operation_type="calculation",
            common_patterns={
                "x": {"type": "number", "minimum": -1000000, "maximum": 1000000},
                "y": {"type": "number", "minimum": -1000000, "maximum": 1000000}
            }
        )
        
        self.register_enhanced_function(
            self.subtract,
            "Subtract two numbers",
            {
                "type": "object",
                "properties": {
                    "x": number_schema.copy(),
                    "y": number_schema.copy()
                },
                "required": ["x", "y"],
                "additionalProperties": False
            },
            operation_type="calculation",
            common_patterns={
                "x": {"type": "number", "minimum": -1000000, "maximum": 1000000},
                "y": {"type": "number", "minimum": -1000000, "maximum": 1000000}
            }
        )
        
        self.register_enhanced_function(
            self.multiply,
            "Multiply two numbers",
            {
                "type": "object",
                "properties": {
                    "x": number_schema.copy(),
                    "y": number_schema.copy()
                },
                "required": ["x", "y"],
                "additionalProperties": False
            },
            operation_type="calculation",
            common_patterns={
                "x": {"type": "number", "minimum": -1000000, "maximum": 1000000},
                "y": {"type": "number", "minimum": -1000000, "maximum": 1000000}
            }
        )
        
        self.register_enhanced_function(
            self.divide,
            "Divide two numbers",
            {
                "type": "object",
                "properties": {
                    "x": number_schema.copy(),
                    "y": number_schema.copy()
                },
                "required": ["x", "y"],
                "additionalProperties": False
            },
            operation_type="calculation",
            common_patterns={
                "x": {"type": "number", "minimum": -1000000, "maximum": 1000000},
                "y": {"type": "number", "minimum": -1000000, "maximum": 1000000}
            }
        )
        
        # Advertise functions
        self._advertise_functions()
    
    def add(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Add two numbers"""
        try:
            # Publish function call event
            self.publish_function_call_event(
                "add",
                {"x": x, "y": y},
                request_info
            )
            
            logger.debug(f"SERVICE: add called with x={x}, y={y}")
            
            # Validate inputs
            self.validate_numeric_input(x, minimum=-1000000, maximum=1000000)
            self.validate_numeric_input(y, minimum=-1000000, maximum=1000000)
            
            # Calculate result
            result = x + y
            
            # Log the result
            logger.info(f"==== CALCULATOR SERVICE: add({x}, {y}) = {result} ====")
            
            # Publish function result event
            self.publish_function_result_event(
                "add",
                {"result": result},
                request_info
            )
            
            return self.format_response({"x": x, "y": y}, result)
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "add",
                e,
                request_info
            )
            raise
    
    def subtract(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Subtract two numbers"""
        try:
            # Publish function call event
            self.publish_function_call_event(
                "subtract",
                {"x": x, "y": y},
                request_info
            )
            
            logger.debug(f"SERVICE: subtract called with x={x}, y={y}")
            
            # Validate inputs
            self.validate_numeric_input(x, minimum=-1000000, maximum=1000000)
            self.validate_numeric_input(y, minimum=-1000000, maximum=1000000)
            
            # Calculate result
            result = x - y
            
            # Log the result
            logger.info(f"==== CALCULATOR SERVICE: subtract({x}, {y}) = {result} ====")
            
            # Publish function result event
            self.publish_function_result_event(
                "subtract",
                {"result": result},
                request_info
            )
            
            return self.format_response({"x": x, "y": y}, result)
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "subtract",
                e,
                request_info
            )
            raise
    
    def multiply(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Multiply two numbers"""
        try:
            # Publish function call event
            self.publish_function_call_event(
                "multiply",
                {"x": x, "y": y},
                request_info
            )
            
            logger.debug(f"SERVICE: multiply called with x={x}, y={y}")
            
            # Validate inputs
            self.validate_numeric_input(x, minimum=-1000000, maximum=1000000)
            self.validate_numeric_input(y, minimum=-1000000, maximum=1000000)
            
            # Calculate result
            result = x * y
            
            # Log the result
            logger.info(f"==== CALCULATOR SERVICE: multiply({x}, {y}) = {result} ====")
            
            # Publish function result event
            self.publish_function_result_event(
                "multiply",
                {"result": result},
                request_info
            )
            
            return self.format_response({"x": x, "y": y}, result)
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "multiply",
                e,
                request_info
            )
            raise
    
    def divide(self, x: float, y: float, request_info=None) -> Dict[str, Any]:
        """Divide two numbers"""
        try:
            # Publish function call event
            self.publish_function_call_event(
                "divide",
                {"x": x, "y": y},
                request_info
            )
            
            logger.debug(f"SERVICE: divide called with x={x}, y={y}")
            
            # Validate inputs
            self.validate_numeric_input(x, minimum=-1000000, maximum=1000000)
            self.validate_numeric_input(y, minimum=-1000000, maximum=1000000)
            if y == 0:
                raise ValueError("Cannot divide by zero")
            
            # Calculate result
            result = x / y
            
            # Log the result
            logger.info(f"==== CALCULATOR SERVICE: divide({x}, {y}) = {result} ====")
            
            # Publish function result event
            self.publish_function_result_event(
                "divide",
                {"result": result},
                request_info
            )
            
            return self.format_response({"x": x, "y": y}, result)
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "divide",
                e,
                request_info
            )
            raise

def main():
    """Main entry point"""
    logger.info("SERVICE: Starting calculator service")
    try:
        # Create and run the calculator service
        service = CalculatorService()
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("SERVICE: Shutting down calculator service")
    except Exception as e:
        logger.error(f"SERVICE: Error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 