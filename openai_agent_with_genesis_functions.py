#!/usr/bin/env python3

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
logger = logging.getLogger("openai_agent_with_genesis_functions")

class OpenAIAgentWithGenesisFunctions(MonitoredAgent):
    """An agent that uses OpenAI API with Genesis function calls"""
    
    def __init__(self, model_name="gpt-4o", classifier_model_name="gpt-4o", domain_id: int = 0,
                 agent_name: str = "OpenAIAgent", service_name: str = "ChatGPT"):
        """Initialize the agent with the specified models
        
        Args:
            model_name: OpenAI model to use (default: gpt-4o)
            classifier_model_name: Model to use for function classification (default: gpt-4o)
            domain_id: DDS domain ID (default: 0)
            agent_name: Name of the agent (default: "OpenAIAgent")
            service_name: Name of the service (default: "ChatGPT")
        """
        logger.info(f"Initializing OpenAIAgentWithGenesisFunctions with model {model_name}")
        
        # Create DDS participant
        participant = dds.DomainParticipant(domain_id)
        
        # Initialize monitored agent base class
        super().__init__(
            agent_name=agent_name,
            service_name=service_name,
            agent_id=str(uuid.uuid4())
        )
        
        # Get API key from environment
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        self.model_name = model_name
        self.classifier_model_name = classifier_model_name
        
        # Initialize generic client for function discovery
        self.generic_client = GenericFunctionClient()
        self.function_cache = {}  # Cache for discovered functions
        
        # Initialize function classifier
        self.function_classifier = FunctionClassifier(llm_client=self.client)
        
        # Set enhanced system prompt with information about function classification
        self.system_prompt = """You are a helpful assistant that can perform various operations using remote services.
You have access to a set of functions that can help you solve problems.
When a function is available that can help with a task, you should use it rather than trying to solve the problem yourself.
This is especially important for mathematical calculations and data processing tasks.
Always explain your reasoning and the steps you're taking."""
        
        logger.info("OpenAIAgentWithGenesisFunctions initialized successfully")
    
    async def _ensure_functions_discovered(self):
        """Ensure functions are discovered before use"""
        if not self.function_cache:
            logger.info("===== TRACING: Starting function discovery =====")
            await self.generic_client.discover_functions()
            
            # Cache discovered functions
            functions = self.generic_client.list_available_functions()
            if not functions:
                logger.info("===== TRACING: No functions available in the system =====")
                return
                
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
                logger.info("===== TRACING: No functions available, proceeding with basic response =====")
                response = {
                    "message": "I understand your request, but I don't have access to any specialized functions at the moment. I'll do my best to help you with the information I have.",
                    "functions_used": []
                }
                return response
            
            # Phase 1: Function Classification
            # Create chain event for classification LLM call start
            chain_event = dds.DynamicData(self.chain_event_type)
            chain_event["chain_id"] = chain_id
            chain_event["call_id"] = call_id
            chain_event["interface_id"] = str(self.app.participant.instance_handle)
            chain_event["primary_agent_id"] = ""
            chain_event["specialized_agent_ids"] = ""
            chain_event["function_id"] = f"openai.{self.classifier_model_name}.classifier"
            chain_event["query_id"] = str(uuid.uuid4())
            chain_event["timestamp"] = int(time.time() * 1000)
            chain_event["event_type"] = "LLM_CALL_START"
            chain_event["source_id"] = str(self.app.participant.instance_handle)
            chain_event["target_id"] = "OpenAI"
            chain_event["status"] = 0
            
            self.chain_event_writer.write(chain_event)
            self.chain_event_writer.flush()
            
            # Get available functions
            available_functions = [
                {
                    "name": name,
                    "description": info["description"],
                    "schema": info["schema"],
                    "classification": info["classification"]
                }
                for name, info in self.function_cache.items()
            ]
            
            # Classify functions based on user query
            relevant_functions = self.function_classifier.classify_functions(
                user_message,
                available_functions,
                self.classifier_model_name
            )
            
            # Create chain event for classification LLM call completion
            chain_event = dds.DynamicData(self.chain_event_type)
            chain_event["chain_id"] = chain_id
            chain_event["call_id"] = call_id
            chain_event["interface_id"] = str(self.app.participant.instance_handle)
            chain_event["primary_agent_id"] = ""
            chain_event["specialized_agent_ids"] = ""
            chain_event["function_id"] = f"openai.{self.classifier_model_name}.classifier"
            chain_event["query_id"] = str(uuid.uuid4())
            chain_event["timestamp"] = int(time.time() * 1000)
            chain_event["event_type"] = "LLM_CALL_COMPLETE"
            chain_event["source_id"] = "OpenAI"
            chain_event["target_id"] = str(self.app.participant.instance_handle)
            chain_event["status"] = 0
            
            self.chain_event_writer.write(chain_event)
            self.chain_event_writer.flush()
            
            # Publish classification results for each relevant function
            for func in relevant_functions:
                # Create chain event for classification result
                chain_event = dds.DynamicData(self.chain_event_type)
                chain_event["chain_id"] = chain_id
                chain_event["call_id"] = call_id
                chain_event["interface_id"] = str(self.app.participant.instance_handle)
                chain_event["primary_agent_id"] = ""
                chain_event["specialized_agent_ids"] = ""
                chain_event["function_id"] = self.function_cache[func["name"]]["function_id"]
                chain_event["query_id"] = str(uuid.uuid4())
                chain_event["timestamp"] = int(time.time() * 1000)
                chain_event["event_type"] = "CLASSIFICATION_RESULT"
                chain_event["source_id"] = str(self.app.participant.instance_handle)
                chain_event["target_id"] = func["name"]
                chain_event["status"] = 0
                
                self.chain_event_writer.write(chain_event)
                self.chain_event_writer.flush()
                
                # Create component lifecycle event for function classification
                self.publish_component_lifecycle_event(
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
                chain_event = dds.DynamicData(self.chain_event_type)
                chain_event["chain_id"] = chain_id
                call_id = str(uuid.uuid4())  # New call ID for this call
                chain_event["call_id"] = call_id
                chain_event["interface_id"] = str(self.app.participant.instance_handle)
                chain_event["primary_agent_id"] = ""
                chain_event["specialized_agent_ids"] = ""
                chain_event["function_id"] = f"openai.{self.model_name}"
                chain_event["query_id"] = str(uuid.uuid4())
                chain_event["timestamp"] = int(time.time() * 1000)
                chain_event["event_type"] = "LLM_CALL_START"
                chain_event["source_id"] = str(self.app.participant.instance_handle)
                chain_event["target_id"] = "OpenAI"
                chain_event["status"] = 0
                
                self.chain_event_writer.write(chain_event)
                self.chain_event_writer.flush()
                
                # Process without functions
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message}
                    ]
                )
                
                # Create chain event for LLM call completion
                chain_event = dds.DynamicData(self.chain_event_type)
                chain_event["chain_id"] = chain_id
                chain_event["call_id"] = call_id
                chain_event["interface_id"] = str(self.app.participant.instance_handle)
                chain_event["primary_agent_id"] = ""
                chain_event["specialized_agent_ids"] = ""
                chain_event["function_id"] = f"openai.{self.model_name}"
                chain_event["query_id"] = str(uuid.uuid4())
                chain_event["timestamp"] = int(time.time() * 1000)
                chain_event["event_type"] = "LLM_CALL_COMPLETE"
                chain_event["source_id"] = "OpenAI"
                chain_event["target_id"] = str(self.app.participant.instance_handle)
                chain_event["status"] = 0
                
                self.chain_event_writer.write(chain_event)
                self.chain_event_writer.flush()
                
                return {
                    "message": response.choices[0].message.content,
                    "status": 0
                }
            
            # Phase 2: Function Execution
            logger.info("===== TRACING: Calling OpenAI API with function schemas =====")
            
            # Create chain event for LLM call start
            chain_event = dds.DynamicData(self.chain_event_type)
            chain_event["chain_id"] = chain_id
            call_id = str(uuid.uuid4())  # New call ID for this call
            chain_event["call_id"] = call_id
            chain_event["interface_id"] = str(self.app.participant.instance_handle)
            chain_event["primary_agent_id"] = ""
            chain_event["specialized_agent_ids"] = ""
            chain_event["function_id"] = f"openai.{self.model_name}"
            chain_event["query_id"] = str(uuid.uuid4())
            chain_event["timestamp"] = int(time.time() * 1000)
            chain_event["event_type"] = "LLM_CALL_START"
            chain_event["source_id"] = str(self.app.participant.instance_handle)
            chain_event["target_id"] = "OpenAI"
            chain_event["status"] = 0
            
            self.chain_event_writer.write(chain_event)
            self.chain_event_writer.flush()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                tools=function_schemas,
                tool_choice="auto"
            )

            logger.info(f"=====!!!!! TRACING: OpenAI response: {response} !!!!!=====")
            
            # Create chain event for LLM call completion
            chain_event = dds.DynamicData(self.chain_event_type)
            chain_event["chain_id"] = chain_id
            chain_event["call_id"] = call_id
            chain_event["interface_id"] = str(self.app.participant.instance_handle)
            chain_event["primary_agent_id"] = ""
            chain_event["specialized_agent_ids"] = ""
            chain_event["function_id"] = f"openai.{self.model_name}"
            chain_event["query_id"] = str(uuid.uuid4())
            chain_event["timestamp"] = int(time.time() * 1000)
            chain_event["event_type"] = "LLM_CALL_COMPLETE"
            chain_event["source_id"] = "OpenAI"
            chain_event["target_id"] = str(self.app.participant.instance_handle)
            chain_event["status"] = 0
            
            self.chain_event_writer.write(chain_event)
            self.chain_event_writer.flush()
            
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
                        function_result = await self._call_function(function_name, **function_args)
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
                    chain_event = dds.DynamicData(self.chain_event_type)
                    chain_event["chain_id"] = chain_id  # Same chain_id to link the calls
                    call_id = str(uuid.uuid4())  # New call_id for this specific call
                    chain_event["call_id"] = call_id
                    chain_event["interface_id"] = str(self.app.participant.instance_handle)
                    chain_event["primary_agent_id"] = ""
                    chain_event["specialized_agent_ids"] = ""
                    chain_event["function_id"] = f"openai.{self.model_name}"
                    chain_event["query_id"] = str(uuid.uuid4())
                    chain_event["timestamp"] = int(time.time() * 1000)
                    chain_event["event_type"] = "LLM_CALL_START"
                    chain_event["source_id"] = str(self.app.participant.instance_handle)
                    chain_event["target_id"] = "OpenAI"
                    chain_event["status"] = 0
                    
                    self.chain_event_writer.write(chain_event)
                    self.chain_event_writer.flush()
                    
                    second_response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_message},
                            message,  # The assistant's message requesting the function call
                            *function_responses  # The function responses
                        ]
                    )
                    
                    # Create chain event for second LLM call completion
                    chain_event = dds.DynamicData(self.chain_event_type)
                    chain_event["chain_id"] = chain_id
                    chain_event["call_id"] = call_id
                    chain_event["interface_id"] = str(self.app.participant.instance_handle)
                    chain_event["primary_agent_id"] = ""
                    chain_event["specialized_agent_ids"] = ""
                    chain_event["function_id"] = f"openai.{self.model_name}"
                    chain_event["query_id"] = str(uuid.uuid4())
                    chain_event["timestamp"] = int(time.time() * 1000)
                    chain_event["event_type"] = "LLM_CALL_COMPLETE"
                    chain_event["source_id"] = "OpenAI"
                    chain_event["target_id"] = str(self.app.participant.instance_handle)
                    chain_event["status"] = 0
                    
                    self.chain_event_writer.write(chain_event)
                    self.chain_event_writer.flush()
                    
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
    
    def close(self):
        """Clean up resources"""
        if self.generic_client:
            self.generic_client.close()
        super().close()

async def run_test():
    """Test the OpenAIAgentWithGenesisFunctions"""
    agent = None
    try:
        # Create agent
        agent = OpenAIAgentWithGenesisFunctions()
        
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
            agent.close()

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