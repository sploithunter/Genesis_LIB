"""
OpenAI function calling agent implementation for the GENESIS library
"""

import logging
import os
import json
import traceback
from typing import Optional, Dict, Any, List, Tuple
from openai import OpenAI
from .openai_chat_agent import OpenAIChatAgent
from .llm import Message
from .function_discovery import FunctionRegistry

class OpenAIFunctionAgent(OpenAIChatAgent):
    """Chat agent using OpenAI models with function calling capabilities"""
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: Optional[str] = None,
                 system_prompt: Optional[str] = None, max_history: int = 10):
        super().__init__(model_name, api_key, system_prompt, max_history)
        self.function_registry = FunctionRegistry()
        self.available_functions = []
        self.logger = logging.getLogger(__name__)
        self.logger.info("===== TRACING: OpenAIFunctionAgent initialized =====")
        
        # Discover available functions
        self._discover_functions()
    
    def _discover_functions(self):
        """Discover available functions from all services"""
        self.logger.info("===== TRACING: Starting function discovery =====")
        
        try:
            # For testing purposes, we'll create a mock function
            # In a real implementation, this would use the function registry's methods
            # to discover functions from the DDS network
            self.available_functions = []
            
            # Add a mock calculator function for testing
            self.available_functions.append({
                "name": "add",
                "function_id": "calculator.add",
                "description": "Add two numbers",
                "schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["a", "b"]
                }
            })
            
            if self.available_functions:
                self.logger.info(f"===== TRACING: Discovered {len(self.available_functions)} functions =====")
                for func in self.available_functions:
                    self.logger.info(f"===== TRACING: Function: {func['name']} ({func['function_id']}) =====")
                    self.logger.info(f"  - Description: {func['description']}")
                    self.logger.info(f"  - Schema: {json.dumps(func['schema'], indent=2)}")
            else:
                self.logger.warning("===== TRACING: No functions discovered =====")
                
        except Exception as e:
            self.logger.error(f"===== TRACING: Error discovering functions: {str(e)} =====")
            self.logger.error(traceback.format_exc())
    
    def _get_function_schemas_for_openai(self):
        """Convert discovered functions to OpenAI function schemas format"""
        self.logger.info("===== TRACING: Converting function schemas for OpenAI =====")
        function_schemas = []
        
        for func in self.available_functions:
            function_schemas.append({
                "type": "function",
                "function": {
                    "name": func["name"],
                    "description": func["description"],
                    "parameters": func["schema"]
                }
            })
            self.logger.info(f"===== TRACING: Added schema for function: {func['name']} =====")
        
        self.logger.info(f"===== TRACING: Total function schemas for OpenAI: {len(function_schemas)} =====")
        return function_schemas
    
    def _call_function(self, function_name: str, **kwargs):
        """Call a function using the function registry"""
        self.logger.info(f"===== TRACING: Calling function {function_name} =====")
        self.logger.info(f"===== TRACING: Function arguments: {json.dumps(kwargs, indent=2)} =====")
        
        # Find the function ID by name
        function_id = None
        for func in self.available_functions:
            if func["name"] == function_name:
                function_id = func["function_id"]
                self.logger.info(f"===== TRACING: Found function ID: {function_id} =====")
                break
        
        if not function_id:
            error_msg = f"Function not found: {function_name}"
            self.logger.error(f"===== TRACING: {error_msg} =====")
            raise ValueError(error_msg)
        
        try:
            # Call the function using the function registry
            self.logger.info(f"===== TRACING: Executing function call to {function_name} ({function_id}) =====")
            
            # For testing purposes, we'll just return a mock result
            # In a real implementation, this would call the function via the registry
            if function_id == "calculator.add":
                result = {"result": kwargs["a"] + kwargs["b"]}
            else:
                result = {"result": f"Mock result for {function_name}"}
            
            # Extract the result value
            if isinstance(result, dict) and "result" in result:
                self.logger.info(f"===== TRACING: Function result: {result['result']} =====")
                return result["result"]
            
            self.logger.info(f"===== TRACING: Function raw result: {result} =====")
            return result
            
        except Exception as e:
            self.logger.error(f"===== TRACING: Error calling function {function_name}: {str(e)} =====")
            self.logger.error(traceback.format_exc())
            raise
    
    def generate_response_with_functions(self, message: str, conversation_id: str) -> Tuple[str, int, bool]:
        """Generate a response using OpenAI with function calling capabilities"""
        self.logger.info(f"===== TRACING: Processing request with functions: {message} =====")
        
        try:
            # Get or create conversation history
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = []
            
            # Add user message
            self.conversations[conversation_id].append(
                Message(role="user", content=message)
            )
            
            # Get function schemas for OpenAI
            function_schemas = self._get_function_schemas_for_openai()
            
            if not function_schemas:
                self.logger.warning("===== TRACING: No function schemas available, processing without functions =====")
                # Process without functions
                response_text, status = super().generate_response(message, conversation_id)
                return response_text, status, False
            
            # Call OpenAI API with function calling
            self.logger.info("===== TRACING: Calling OpenAI API with function schemas =====")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt if self.system_prompt else "You are a helpful AI assistant."},
                    *[{"role": msg.role, "content": msg.content} for msg in self.conversations[conversation_id]]
                ],
                tools=function_schemas,
                tool_choice="auto"
            )
            
            # Extract the response
            message_obj = response.choices[0].message
            
            # Check if the model wants to call a function
            if message_obj.tool_calls:
                self.logger.info(f"===== TRACING: Model requested function call(s): {len(message_obj.tool_calls)} =====")
                
                # Process each function call
                function_responses = []
                for tool_call in message_obj.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    self.logger.info(f"===== TRACING: Processing function call: {function_name} =====")
                    
                    # Call the function
                    try:
                        function_result = self._call_function(function_name, **function_args)
                        function_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": str(function_result)
                        })
                        self.logger.info(f"===== TRACING: Function {function_name} returned: {function_result} =====")
                    except Exception as e:
                        self.logger.error(f"===== TRACING: Error calling function {function_name}: {str(e)} =====")
                        function_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": f"Error: {str(e)}"
                        })
                
                # If we have function responses, send them back to the model
                if function_responses:
                    # Create a new conversation with the function responses
                    self.logger.info("===== TRACING: Sending function responses back to OpenAI =====")
                    second_response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": self.system_prompt if self.system_prompt else "You are a helpful AI assistant."},
                            *[{"role": msg.role, "content": msg.content} for msg in self.conversations[conversation_id]],
                            {"role": "assistant", "content": message_obj.content, "tool_calls": message_obj.tool_calls},
                            *function_responses
                        ]
                    )
                    
                    # Extract the final response
                    final_message = second_response.choices[0].message.content
                    self.logger.info(f"===== TRACING: Final response: {final_message} =====")
                    
                    # Add assistant response to conversation history
                    self.conversations[conversation_id].append(
                        Message(role="assistant", content=final_message)
                    )
                    
                    # Cleanup old conversations
                    self._cleanup_old_conversations()
                    
                    return final_message, 0, True
            
            # If no function call, just return the response
            text_response = message_obj.content
            self.logger.info(f"===== TRACING: Response (no function call): {text_response} =====")
            
            # Add assistant response to conversation history
            self.conversations[conversation_id].append(
                Message(role="assistant", content=text_response)
            )
            
            # Cleanup old conversations
            self._cleanup_old_conversations()
            
            return text_response, 0, False
                
        except Exception as e:
            self.logger.error(f"===== TRACING: Error processing request: {str(e)} =====")
            self.logger.error(traceback.format_exc())
            return f"Error: {str(e)}", 1, False 