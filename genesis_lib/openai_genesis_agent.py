#!/usr/bin/env python3
"""
OpenAI Genesis Agent Implementation

This module defines the OpenAIGenesisAgent class, which extends the MonitoredAgent
to provide an agent implementation specifically utilizing the OpenAI API.
It integrates OpenAI's chat completion capabilities, including function calling,
with the Genesis framework's monitoring and function discovery features.

Copyright (c) 2025, RTI & Jason Upchurch
"""

"""
OpenAI Genesis agent with function calling capabilities.
This agent provides a flexible and configurable interface for creating OpenAI-based agents
with support for function discovery, classification, and execution.
"""

import os
import sys
import logging
import json
import asyncio
import time
import traceback
import uuid
from openai import OpenAI
from typing import Dict, Any, List, Optional

from genesis_lib.monitored_agent import MonitoredAgent
from genesis_lib.function_classifier import FunctionClassifier
from genesis_lib.generic_function_client import GenericFunctionClient
import rti.connextdds as dds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openai_genesis_agent")

class OpenAIGenesisAgent(MonitoredAgent):
    """An agent that uses OpenAI API with Genesis function calls"""
    
    def __init__(self, model_name="gpt-4o", classifier_model_name="gpt-4o-mini", domain_id: int = 0,
                 agent_name: str = "OpenAIAgent", description: str = None, enable_tracing: bool = False):
        """Initialize the agent with the specified models
        
        Args:
            model_name: OpenAI model to use (default: gpt-4o)
            classifier_model_name: Model to use for function classification (default: gpt-4o-mini)
            domain_id: DDS domain ID (default: 0)
            agent_name: Name of the agent (default: "OpenAIAgent")
            description: Optional description of the agent
            enable_tracing: Whether to enable detailed tracing logs (default: False)
        """
        # Store tracing configuration
        self.enable_tracing = enable_tracing
        
        if self.enable_tracing:
            logger.info(f"Initializing OpenAIGenesisAgent with model {model_name}")
        
        # Store model configuration
        self.model_config = {
            "model_name": model_name,
            "classifier_model_name": classifier_model_name
        }
        
        # Initialize monitored agent base class
        super().__init__(
            agent_name=agent_name,
            service_name="ChatGPT",
            agent_type="SPECIALIZED_AGENT",  # This is a specialized AI agent
            description=description or f"An OpenAI-powered agent using {model_name} model",
            domain_id=domain_id
        )
        
        # Get API key from environment
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        # Initialize generic client for function discovery, passing the agent's participant
        self.generic_client = GenericFunctionClient(participant=self.app.participant)
        self.function_cache = {}  # Cache for discovered functions
        
        # Initialize function classifier
        self.function_classifier = FunctionClassifier(llm_client=self.client)
        
        # Set system prompts for different scenarios
        self.function_based_system_prompt = """You are a helpful assistant that can perform various operations using remote services.
You have access to a set of functions that can help you solve problems.
When a function is available that can help with a task, you should use it rather than trying to solve the problem yourself.
This is especially important for mathematical calculations and data processing tasks.
Always explain your reasoning and the steps you're taking."""

        self.general_system_prompt = """You are a helpful and engaging AI assistant. You can:
- Answer questions and provide information
- Tell jokes and engage in casual conversation
- Help with creative tasks like writing and brainstorming
- Provide explanations and teach concepts
- Assist with problem-solving and decision making
Be friendly, professional, and maintain a helpful tone while being concise and clear in your responses."""

        # Start with general prompt, will switch to function-based if functions are discovered
        self.system_prompt = self.general_system_prompt
        
        # Set OpenAI-specific capabilities
        self.set_agent_capabilities(
            supported_tasks=["text_generation", "conversation"],
            additional_capabilities=self.model_config
        )
        
        if self.enable_tracing:
            logger.info("OpenAIGenesisAgent initialized successfully")
    
    async def _ensure_functions_discovered(self):
        """Ensure functions are discovered before use"""
        if not self.function_cache:
            logger.info("===== DDS TRACE: Function cache empty, calling generic_client.discover_functions... =====")
            await self.generic_client.discover_functions()
            logger.info("===== DDS TRACE: generic_client.discover_functions returned. =====")

            # Cache discovered functions
            functions = self.generic_client.list_available_functions()
            if not functions:
                logger.info("===== TRACING: No functions available in the system =====")
                # Use general system prompt since no functions are available
                self.system_prompt = self.general_system_prompt
                return
                
            # Switch to function-based prompt since functions are available
            self.system_prompt = self.function_based_system_prompt
            
            for func in functions:
                self.function_cache[func["name"]] = {
                    "function_id": func["function_id"],
                    "description": func["description"],
                    "schema": func["schema"],
                    "classification": {
                        "entity_type": "function",
                        "domain": ["unknown"],
                        "operation_type": func.get("operation_type", "unknown"),
                        "io_types": {
                            "input": ["unknown"],
                            "output": ["unknown"]
                        },
                        "performance": {
                            "latency": "unknown",
                            "throughput": "unknown"
                        },
                        "security": {
                            "level": "public",
                            "authentication": "none"
                        }
                    }
                }
                
                logger.info("===== TRACING: Discovered function =====")
                logger.info(f"Name: {func['name']}")
                logger.info(f"ID: {func['function_id']}")
                logger.info(f"Description: {func['description']}")
                logger.info(f"Schema: {json.dumps(func['schema'], indent=2)}")
                logger.info("=" * 80)
                
                # Publish discovery event
                self.publish_monitoring_event(
                    "AGENT_DISCOVERY",
                    metadata={
                        "function_id": func["function_id"],
                        "function_name": func["name"]
                    }
                )
    
    def _get_function_schemas_for_openai(self, relevant_functions: Optional[List[str]] = None):
        """Convert discovered functions to OpenAI function schemas format"""
        logger.info("===== TRACING: Converting function schemas for OpenAI =====")
        function_schemas = []
        
        for name, func_info in self.function_cache.items():
            # If relevant_functions is provided, only include those functions
            if relevant_functions is not None and name not in relevant_functions:
                continue
                
            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": func_info["description"],
                    "parameters": func_info["schema"]
                }
            }
            function_schemas.append(schema)
            logger.info(f"===== TRACING: Added schema for function: {name} =====")
        
        return function_schemas
    
    async def _call_function(self, function_name: str, **kwargs) -> Any:
        """Call a function using the generic client"""
        logger.info(f"===== TRACING: Calling function {function_name} =====")
        logger.info(f"===== TRACING: Function arguments: {json.dumps(kwargs, indent=2)} =====")
        
        if function_name not in self.function_cache:
            error_msg = f"Function not found: {function_name}"
            logger.error(f"===== TRACING: {error_msg} =====")
            raise ValueError(error_msg)
        
        try:
            # Call the function through the generic client
            start_time = time.time()
            result = await self.generic_client.call_function(
                self.function_cache[function_name]["function_id"],
                **kwargs
            )
            end_time = time.time()
            
            logger.info(f"===== TRACING: Function call completed in {end_time - start_time:.2f} seconds =====")
            logger.info(f"===== TRACING: Function result: {result} =====")
            
            # Extract result value if in dict format
            if isinstance(result, dict) and "result" in result:
                return result["result"]
            return result
            
        except Exception as e:
            logger.error(f"===== TRACING: Error calling function {function_name}: {str(e)} =====")
            logger.error(traceback.format_exc())
            raise
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a user request and return a response"""
        user_message = request.get("message", "")
        logger.info(f"===== TRACING: Processing request: {user_message} =====")
        
        try:
            # Ensure functions are discovered
            await self._ensure_functions_discovered()
            
            # Generate chain and call IDs for tracking
            chain_id = str(uuid.uuid4())
            call_id = str(uuid.uuid4())
            
            # If no functions are available, proceed with basic response
            if not self.function_cache:
                logger.info("===== TRACING: No functions available, proceeding with general conversation =====")
                
                # Create chain event for LLM call start
                self._publish_llm_call_start(
                    chain_id=chain_id,
                    call_id=call_id,
                    model_identifier=f"openai.{self.model_config['model_name']}"
                )
                
                # Process with general conversation
                response = self.client.chat.completions.create(
                    model=self.model_config['model_name'],
                    messages=[
                        {"role": "system", "content": self.general_system_prompt},
                        {"role": "user", "content": user_message}
                    ]
                )
                
                # Create chain event for LLM call completion
                self._publish_llm_call_complete(
                    chain_id=chain_id,
                    call_id=call_id,
                    model_identifier=f"openai.{self.model_config['model_name']}"
                )
                
                return {
                    "message": response.choices[0].message.content,
                    "status": 0
                }
            
            # Phase 1: Function Classification
            # Create chain event for classification LLM call start
            self._publish_llm_call_start(
                chain_id=chain_id,
                call_id=call_id,
                model_identifier=f"openai.{self.model_config['classifier_model_name']}.classifier"
            )
            
            # Get available functions
            available_functions = [
                {
                    "name": name,
                    "description": info["description"],
                    "schema": info["schema"],
                    "classification": info.get("classification", {})
                }
                for name, info in self.function_cache.items()
            ]
            
            # Classify functions based on user query
            relevant_functions = self.function_classifier.classify_functions(
                user_message,
                available_functions,
                self.model_config['classifier_model_name']
            )
            
            # Create chain event for classification LLM call completion
            self._publish_llm_call_complete(
                chain_id=chain_id,
                call_id=call_id,
                model_identifier=f"openai.{self.model_config['classifier_model_name']}.classifier"
            )
            
            # Publish classification results for each relevant function
            for func in relevant_functions:
                # Create chain event for classification result
                self._publish_classification_result(
                    chain_id=chain_id,
                    call_id=call_id,
                    classified_function_name=func["name"],
                    classified_function_id=self.function_cache[func["name"]]["function_id"]
                )
                
                # Create component lifecycle event for function classification
                self.publish_component_lifecycle_event(
                    category="STATE_CHANGE",
                    previous_state="READY",
                    new_state="BUSY",
                    reason=f"CLASSIFICATION.RELEVANT: Function '{func['name']}' for query: {user_message[:100]}",
                    capabilities=json.dumps({
                        "function_name": func["name"],
                        "description": func["description"],
                        "classification": func["classification"]
                    })
                )
            
            # Get function schemas for relevant functions
            relevant_function_names = [func["name"] for func in relevant_functions]
            function_schemas = self._get_function_schemas_for_openai(relevant_function_names)
            
            if not function_schemas:
                logger.warning("===== TRACING: No relevant functions found, processing without functions =====")
                
                # Create chain event for LLM call start
                self._publish_llm_call_start(
                    chain_id=chain_id,
                    call_id=call_id,
                    model_identifier=f"openai.{self.model_config['model_name']}"
                )
                
                # Process without functions
                response = self.client.chat.completions.create(
                    model=self.model_config['model_name'],
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message}
                    ]
                )
                
                # Create chain event for LLM call completion
                self._publish_llm_call_complete(
                    chain_id=chain_id,
                    call_id=call_id,
                    model_identifier=f"openai.{self.model_config['model_name']}"
                )
                
                return {
                    "message": response.choices[0].message.content,
                    "status": 0
                }
            
            # Phase 2: Function Execution
            logger.info("===== TRACING: Calling OpenAI API with function schemas =====")
            
            # Create chain event for LLM call start
            self._publish_llm_call_start(
                chain_id=chain_id,
                call_id=call_id,
                model_identifier=f"openai.{self.model_config['model_name']}"
            )
            
            response = self.client.chat.completions.create(
                model=self.model_config['model_name'],
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                tools=function_schemas,
                tool_choice="auto"
            )

            logger.info(f"=====!!!!! TRACING: OpenAI response: {response} !!!!!=====")
            
            # Create chain event for LLM call completion
            self._publish_llm_call_complete(
                chain_id=chain_id,
                call_id=call_id,
                model_identifier=f"openai.{self.model_config['model_name']}"
            )
            
            # Extract the response
            message = response.choices[0].message
            
            # Check if the model wants to call a function
            if message.tool_calls:
                logger.info(f"===== TRACING: Model requested function call(s): {len(message.tool_calls)} =====")
                
                # Process each function call
                function_responses = []
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"===== TRACING: Processing function call: {function_name} =====")
                    
                    # Call the function
                    try:
                        # Create chain event for function call start
                        self._publish_function_call_start(
                            chain_id=chain_id,
                            call_id=call_id,
                            function_name=function_name,
                            function_id=self.function_cache[function_name]["function_id"],
                            target_provider_id=self.function_cache[function_name].get("provider_id")
                        )
                        
                        # Call the function through the generic client
                        start_time = time.time()
                        function_result = await self._call_function(function_name, **function_args)
                        end_time = time.time()
                        
                        # Create chain event for function call completion
                        self._publish_function_call_complete(
                            chain_id=chain_id,
                            call_id=call_id,
                            function_name=function_name,
                            function_id=self.function_cache[function_name]["function_id"],
                            source_provider_id=self.function_cache[function_name].get("provider_id")
                        )
                        
                        logger.info(f"===== TRACING: Function call completed in {end_time - start_time:.2f} seconds =====")
                        logger.info(f"===== TRACING: Function result: {function_result} =====")
                        
                        # Extract result value if in dict format
                        if isinstance(function_result, dict) and "result" in function_result:
                            function_result = function_result["result"]
                            
                        function_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": str(function_result)
                        })
                        logger.info(f"===== TRACING: Function {function_name} returned: {function_result} =====")
                    except Exception as e:
                        logger.error(f"===== TRACING: Error calling function {function_name}: {str(e)} =====")
                        function_responses.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": f"Error: {str(e)}"
                        })
                
                # If we have function responses, send them back to the model
                if function_responses:
                    # Create a new conversation with the function responses
                    logger.info("===== TRACING: Sending function responses back to OpenAI =====")
                    
                    # Create chain event for second LLM call start
                    self._publish_llm_call_start(
                        chain_id=chain_id,
                        call_id=call_id,
                        model_identifier=f"openai.{self.model_config['model_name']}"
                    )
                    
                    second_response = self.client.chat.completions.create(
                        model=self.model_config['model_name'],
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_message},
                            message,  # The assistant's message requesting the function call
                            *function_responses  # The function responses
                        ]
                    )
                    
                    # Create chain event for second LLM call completion
                    self._publish_llm_call_complete(
                        chain_id=chain_id,
                        call_id=call_id,
                        model_identifier=f"openai.{self.model_config['model_name']}"
                    )
                    
                    # Extract the final response
                    final_message = second_response.choices[0].message.content
                    logger.info(f"===== TRACING: Final response: {final_message} =====")
                    return {"message": final_message, "status": 0}
            
            # If no function call, just return the response
            text_response = message.content
            logger.info(f"===== TRACING: Response (no function call): {text_response} =====")
            return {"message": text_response, "status": 0}
                
        except Exception as e:
            logger.error(f"===== TRACING: Error processing request: {str(e)} =====")
            logger.error(traceback.format_exc())
            return {"message": f"Error: {str(e)}", "status": 1}
    
    async def close(self):
        """Clean up resources"""
        try:
            # Close OpenAI-specific resources
            if hasattr(self, 'generic_client') and self.generic_client is not None:
                if asyncio.iscoroutinefunction(self.generic_client.close):
                    await self.generic_client.close()
                else:
                    self.generic_client.close()
            
            # Close base class resources
            await super().close()
            
            logger.info(f"OpenAIGenesisAgent closed successfully")
        except Exception as e:
            logger.error(f"Error closing OpenAIGenesisAgent: {str(e)}")
            logger.error(traceback.format_exc())

    async def process_message(self, message: str) -> str:
        """
        Process a message using OpenAI and return the response.
        This method is monitored by the Genesis framework.
        
        Args:
            message: The message to process
            
        Returns:
            The agent's response to the message
        """
        try:
            # Process the message using OpenAI's process_request method
            response = await self.process_request({"message": message})
            
            # Publish a monitoring event for the successful response
            self.publish_monitoring_event(
                event_type="AGENT_RESPONSE",
                result_data={"response": response}
            )
            
            return response.get("message", "No response generated")
            
        except Exception as e:
            # Publish a monitoring event for the error
            self.publish_monitoring_event(
                event_type="AGENT_STATUS",
                status_data={"error": str(e)}
            )
            raise

async def run_test():
    """Test the OpenAIGenesisAgent"""
    agent = None
    try:
        # Create agent
        agent = OpenAIGenesisAgent()
        
        # Test with a single request to test the calculator service
        test_message = "What is 31337 multiplied by 424242?"
        
        logger.info(f"\n===== Testing agent with message: {test_message} =====")
        
        # Process request
        result = await agent.process_request({"message": test_message})
        
        # Print result
        if 'status' in result:
            logger.info(f"Result status: {result['status']}")
        logger.info(f"Response: {result['message']}")
        logger.info("=" * 50)
        
        return 0
    except Exception as e:
        logger.error(f"Error in test: {str(e)}", exc_info=True)
        return 1
    finally:
        # Clean up
        if agent:
            await agent.close()

def main():
    """Main entry point"""
    try:
        return asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.info("Test interrupted")
        return 0
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main()) 