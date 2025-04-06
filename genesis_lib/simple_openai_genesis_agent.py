#!/usr/bin/env python3

"""
Simple OpenAI Genesis Agent

This is a minimal implementation that provides a clean interface for OpenAI integration.
"""

import os
import sys
import logging
import json
import time
import traceback
from typing import Dict, Any, List, Optional, Tuple, Union
import uuid
import asyncio
import threading
import queue

from openai import OpenAI
import rti.connextdds as dds
import rti.rpc as rpc

from genesis_lib.agent import GenesisAgent
from genesis_lib.function_discovery import FunctionRegistry
from genesis_lib.function_classifier import FunctionClassifier
from genesis_lib.function_client import GenericFunctionClient
from genesis_lib.utils import (
    convert_functions_to_openai_schema, 
    call_function_thread_safe, 
    find_function_by_name, 
    filter_functions_by_relevance,
    generate_response_with_functions
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("simple_openai_genesis_agent")

class SimpleOpenAIGenesisAgent(GenesisAgent):
    """
    This agent provides a clean interface for OpenAI integration and function discovery.
    """
    
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: Optional[str] = None,
                 system_prompt: Optional[str] = None):
        """
        Initialize the agent with the specified model.
        
        Args:
            model_name: The OpenAI model to use (default: gpt-3.5-turbo)
            api_key: OpenAI API key (if None, will use OPENAI_API_KEY environment variable)
            system_prompt: Custom system prompt to use (if None, will use a default prompt)
        """
        # Initialize the GenesisAgent base class
        super().__init__(agent_name="SimpleOpenAIGenesisAgent", service_name="Chat")
        
        logger.info(f"Initializing SimpleOpenAIGenesisAgent with model {model_name}")
        
        # Get API key from environment if not provided
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        
        # Initialize function client
        self.function_client = GenericFunctionClient()
        
        # Initialize function classifier
        self.function_classifier = FunctionClassifier(llm_client=self.client)
        
        # Store discovered functions
        self.available_functions = []
        
        # Initialize conversation history storage
        self.conversation_histories = {}
        
        # Discover available functions
        self._discover_functions()
        
        # Set system prompt
        self.system_prompt = system_prompt or "You are a helpful assistant that can use functions to solve problems."
        
        logger.info("SimpleOpenAIGenesisAgent initialized successfully")
    
    def _discover_functions(self):
        """
        Discover available functions from all services.
        This method populates the available_functions list with function metadata.
        """
        # Use the base class implementation to discover functions
        self.available_functions = super().discover_functions(self.function_client)

    def _get_function_schemas_for_openai(self):
        """Convert discovered functions to OpenAI function schemas format"""
        return convert_functions_to_openai_schema(self.available_functions)
    
    def _call_function(self, function_name: str, **kwargs):
        """
        Call a function by name with the given arguments.
        Uses a separate thread for DDS operations to avoid exclusive area problems.
        
        Args:
            function_name: Name of the function to call
            **kwargs: Arguments to pass to the function
            
        Returns:
            Function result
            
        Raises:
            ValueError: If function is not found
            RuntimeError: If function execution fails
        """
        logger.info(f"===== TRACING: Calling function {function_name} =====")
        logger.info(f"===== TRACING: Function arguments: {json.dumps(kwargs, indent=2)} =====")
        
        # Find the function ID and service name by name
        function_id, service_name = find_function_by_name(self.available_functions, function_name)
        
        if not function_id:
            error_msg = f"Function not found: {function_name}"
            logger.error(f"===== TRACING: {error_msg} =====")
            raise ValueError(error_msg)
        
        # Call the function using the thread-safe utility
        return call_function_thread_safe(
            function_client=self.function_client,
            function_name=function_name,
            function_id=function_id,
            service_name=service_name,
            **kwargs
        )
    
    def generate_response_with_functions(self, message: str, conversation_id: str) -> Tuple[str, int, bool]:
        """
        Generate a response using OpenAI API with function calling capabilities.
        
        Args:
            message: The user's message
            conversation_id: A unique ID for the conversation
            
        Returns:
            Tuple of (response, status, used_functions)
        """
        # Get or initialize conversation history
        conversation_history = self.conversation_histories.get(conversation_id, [])
        
        # Filter functions by relevance to the message
        relevant_functions = filter_functions_by_relevance(message, self.available_functions, self.function_classifier)
        
        # Generate response using the utility function
        response, status, used_functions, updated_history = generate_response_with_functions(
            client=self.client,
            message=message,
            model_name=self.model_name,
            system_prompt=self.system_prompt,
            relevant_functions=relevant_functions,
            call_function_handler=self._call_function,
            conversation_history=conversation_history,
            conversation_id=conversation_id
        )
        
        # Update conversation history
        if updated_history:
            self.conversation_histories[conversation_id] = updated_history
            
            # Limit conversation history to last 10 messages to prevent excessive memory usage
            if len(self.conversation_histories[conversation_id]) > 10:
                # Keep the system message and the last 9 messages
                system_message = next((m for m in self.conversation_histories[conversation_id] if m["role"] == "system"), None)
                recent_messages = self.conversation_histories[conversation_id][-9:]
                
                if system_message:
                    self.conversation_histories[conversation_id] = [system_message] + recent_messages
                else:
                    self.conversation_histories[conversation_id] = recent_messages
        
        return response, status, used_functions
    
    def process_request(self, request: Any) -> Dict[str, Any]:
        """
        Process a request from the DDS service.
        
        Args:
            request: DDS request object
            
        Returns:
            Dictionary with response data
        """
        message = request["message"]
        conversation_id = request["conversation_id"]
        
        response, status, used_functions = self.generate_response_with_functions(message, conversation_id)
        
        return {
            "response": response,
            "status": status
        }
    
    def close(self):
        """Clean up resources"""
        logger.info("===== TRACING: Closing function registry =====")
        self.function_registry.close()

def main():
    """Run the SimpleOpenAIGenesisAgent"""
    agent = None
    try:
        # Create agent
        agent = SimpleOpenAIGenesisAgent()
        
        # Run agent
        agent.run()
        
        return 0
    except KeyboardInterrupt:
        logger.info("\nShutting down SimpleOpenAIGenesisAgent...")
        return 0
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        return 1
    finally:
        # Clean up
        if agent:
            agent.close()

if __name__ == "__main__":
    sys.exit(main()) 