#!/usr/bin/env python3

import logging
import asyncio
from genesis_lib.enhanced_service_base import EnhancedServiceBase
from typing import Dict, Any, List
import json
from genesis_lib.function_discovery import FunctionRegistry

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("text_processor_service")

class TextProcessorService(EnhancedServiceBase):
    """Implementation of the text processor service using Genesis RPC framework"""
    
    def __init__(self):
        """Initialize the text processor service"""
        super().__init__(service_name="TextProcessorService", capabilities=["text_processor", "text_manipulation"])
        
        # Get DDS instance handle for consistent identification
        self.app_guid = str(self.participant.instance_handle)
        
        # Initialize the function registry
        self.registry = FunctionRegistry(participant=self.participant)
        
        # Get common schemas
        text_schema = self.get_common_schema("text")
        
        # Register text processing functions with OpenAI-style schemas
        self.register_enhanced_function(
            self.transform_case,
            "Transform text to specified case (upper, lower, or title)",
            {
                "type": "object",
                "properties": {
                    "text": text_schema.copy(),
                    "case": {
                        "type": "string",
                        "description": "Target case transformation to apply",
                        "enum": ["upper", "lower", "title"],
                        "examples": ["upper", "lower", "title"]
                    }
                },
                "required": ["text", "case"],
                "additionalProperties": False
            },
            operation_type="transformation",
            common_patterns={
                "text": {"type": "text", "min_length": 1},
                "case": {"type": "enum", "values": ["upper", "lower", "title"]}
            }
        )
        
        self.register_enhanced_function(
            self.analyze_text,
            "Analyze text and return detailed statistics about its composition",
            {
                "type": "object",
                "properties": {
                    "text": text_schema.copy()
                },
                "required": ["text"],
                "additionalProperties": False
            },
            operation_type="analysis",
            common_patterns={
                "text": {"type": "text", "min_length": 1}
            }
        )
        
        self.register_enhanced_function(
            self.generate_text,
            "Generate text by repeating or padding the input text",
            {
                "type": "object",
                "properties": {
                    "text": text_schema.copy(),
                    "operation": {
                        "type": "string",
                        "description": "Operation to perform on the text",
                        "enum": ["repeat", "pad"],
                        "examples": ["repeat", "pad"]
                    },
                    "count": {
                        "type": "integer",
                        "description": "For 'repeat': number of times to repeat the text. For 'pad': length of padding on each side",
                        "minimum": 0,
                        "maximum": 1000,
                        "examples": [2, 5, 10]
                    }
                },
                "required": ["text", "operation", "count"],
                "additionalProperties": False
            },
            operation_type="generation",
            common_patterns={
                "text": {"type": "text", "min_length": 1},
                "operation": {"type": "enum", "values": ["repeat", "pad"]},
                "count": {"type": "number", "minimum": 0, "maximum": 1000}
            }
        )
        
        # Advertise functions to the registry
        self._advertise_functions()
    
    def transform_case(self, text: str, case: str, request_info=None) -> Dict[str, Any]:
        """
        Transform text to specified case
        
        Args:
            text: Text to transform
            case: Target case (upper, lower, or title)
            request_info: Request information containing client ID
            
        Returns:
            Dictionary containing input parameters and transformed result
            
        Raises:
            ValueError: If text is empty or case is not supported
        """
        try:
            # Publish function call event
            self.publish_function_call_event(
                "transform_case",
                {"text": text, "case": case},
                request_info
            )
            
            logger.debug(f"SERVICE: transform_case called with text='{text}', case='{case}'")
            
            # Validate inputs
            self.validate_text_input(text, min_length=1)
            if case not in ["upper", "lower", "title"]:
                raise ValueError(f"Unsupported case: {case}. Must be one of: upper, lower, title")
            
            # Transform text
            if case == "upper":
                result = text.upper()
            elif case == "lower":
                result = text.lower()
            else:  # title
                result = text.title()
            
            response = self.format_response(
                {"text": text, "case": case},
                {"result": result}
            )
            
            # Publish function result event
            self.publish_function_result_event(
                "transform_case",
                {"result": response},
                request_info
            )
            
            return response
            
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "transform_case",
                e,
                request_info
            )
            raise
    
    def analyze_text(self, text: str, request_info=None) -> Dict[str, Any]:
        """
        Analyze text and return detailed statistics
        
        Args:
            text: Text to analyze
            request_info: Request information containing client ID
            
        Returns:
            Dictionary containing input parameters and various statistics
            
        Raises:
            ValueError: If text is empty
        """
        try:
            # Publish function call event
            self.publish_function_call_event(
                "analyze_text",
                {"text": text},
                request_info
            )
            
            logger.debug(f"SERVICE: analyze_text called with text='{text}'")
            
            # Validate input
            self.validate_text_input(text, min_length=1)
            
            # Count various character types
            alpha_count = sum(c.isalpha() for c in text)
            digit_count = sum(c.isdigit() for c in text)
            space_count = sum(c.isspace() for c in text)
            punct_count = sum(not c.isalnum() and not c.isspace() for c in text)
            
            response = self.format_response(
                {"text": text},
                {
                    "statistics": {
                        "total_length": len(text),
                        "alpha_count": alpha_count,
                        "digit_count": digit_count,
                        "space_count": space_count,
                        "punctuation_count": punct_count,
                        "word_count": len(text.split()),
                        "line_count": len(text.splitlines()) or 1,
                        "uppercase_count": sum(c.isupper() for c in text),
                        "lowercase_count": sum(c.islower() for c in text)
                    }
                }
            )
            
            # Publish function result event
            self.publish_function_result_event(
                "analyze_text",
                {"result": response},
                request_info
            )
            
            return response
            
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "analyze_text",
                e,
                request_info
            )
            raise
    
    def generate_text(self, text: str, operation: str, count: int, request_info=None) -> Dict[str, Any]:
        """
        Generate text based on input text and specified operation
        
        Args:
            text: Base text for generation
            operation: Operation to perform (repeat or pad)
            count: Number of repetitions or padding length
            request_info: Request information containing client ID
            
        Returns:
            Dictionary containing input parameters and generated result
            
        Raises:
            ValueError: If text is empty, operation is invalid, or count is out of range
        """
        try:
            # Publish function call event
            self.publish_function_call_event(
                "generate_text",
                {"text": text, "operation": operation, "count": count},
                request_info
            )
            
            logger.debug(f"SERVICE: generate_text called with text='{text}', operation='{operation}', count={count}")
            
            # Validate inputs
            self.validate_text_input(text, min_length=1)
            if operation not in ["repeat", "pad"]:
                raise ValueError(f"Unsupported operation: {operation}. Must be one of: repeat, pad")
            if not isinstance(count, int):
                raise ValueError("Count must be an integer")
            if count < 0:
                raise ValueError("Count must be non-negative")
            if count > 1000:
                raise ValueError("Count cannot exceed 1000")
            
            # Generate text
            if operation == "repeat":
                result = text * count
            else:  # pad
                padding = "-" * count
                result = padding + text + padding
            
            response = self.format_response(
                {"text": text, "operation": operation, "count": count},
                {
                    "result": result,
                    "result_length": len(result)
                }
            )
            
            # Publish function result event
            self.publish_function_result_event(
                "generate_text",
                {"result": response},
                request_info
            )
            
            return response
            
        except Exception as e:
            # Publish function error event
            self.publish_function_error_event(
                "generate_text",
                e,
                request_info
            )
            raise

def main():
    """Main entry point"""
    logger.info("SERVICE: Starting text processor service")
    try:
        # Create and run the text processor service
        service = TextProcessorService()
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("SERVICE: Shutting down text processor service")
    except Exception as e:
        logger.error(f"SERVICE: Error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 