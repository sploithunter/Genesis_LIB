"""
Base agent class for the GENESIS library.
"""

import sys
import time
import logging
import os
import json
import asyncio
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import rti.connextdds as dds
import rti.rpc as rpc
from .genesis_app import GenesisApp
from .llm import ChatAgent, AnthropicChatAgent
from .utils import get_datamodel_path

# Get logger
logger = logging.getLogger(__name__)

class GenesisAgent(ABC):
    """Base class for all Genesis agents"""
    def __init__(self, agent_name: str, service_name: str, agent_id: str = None):
        """
        Initialize the agent.
        
        Args:
            agent_name: Name of the agent
            service_name: Name of the service this agent provides
            agent_id: Optional UUID for the agent (if None, will generate one)
        """
        self.agent_name = agent_name
        self.service_name = service_name
        self.app = GenesisApp(preferred_name=self.agent_name, agent_id=agent_id)
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.request_type = self.type_provider.type("genesis_lib", f"{service_name}Request")
        self.reply_type = self.type_provider.type("genesis_lib", f"{service_name}Reply")
        
        # Create replier
        self.replier = rpc.Replier(
            request_type=self.request_type,
            reply_type=self.reply_type,
            participant=self.app.participant,
            service_name=self.service_name,
            on_request_available=self.on_request
        )
        
        # Store discovered functions
        self.discovered_functions = []

    def discover_functions(self, function_client, max_retries: int = 5) -> List[Dict[str, Any]]:
        """
        Discover available functions from all services using the provided function client.
        
        Args:
            function_client: An instance of a function client (e.g., GenericFunctionClient)
            max_retries: Maximum number of retries for function discovery
            
        Returns:
            List of discovered functions
        """
        logger.info("===== TRACING: Starting function discovery =====")
        
        # Store discovered functions
        available_functions = []
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Create event loop for async calls
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Discover functions using the client
                logger.info("===== TRACING: Calling discover_functions on function client =====")
                loop.run_until_complete(function_client.discover_functions())
                
                # Get the list of available functions
                available_functions = function_client.list_available_functions()
                
                # Close the loop
                loop.close()
                
                if available_functions:
                    logger.info(f"===== TRACING: Discovered {len(available_functions)} functions =====")
                    for func in available_functions:
                        logger.info(f"===== TRACING: Function: {func['name']} ({func['function_id']}) =====")
                        logger.info(f"  - Description: {func['description']}")
                        logger.info(f"  - Schema: {json.dumps(func['schema'], indent=2)}")
                    
                    # Store discovered functions in the agent instance
                    self.discovered_functions = available_functions
                    
                    break
                else:
                    logger.warning("===== TRACING: No functions discovered, retrying... =====")
                    retry_count += 1
                    time.sleep(1)
            except Exception as e:
                logger.error(f"===== TRACING: Error discovering functions: {str(e)} =====")
                logger.error(traceback.format_exc())
                retry_count += 1
                time.sleep(1)
                
        if retry_count >= max_retries:
            logger.warning("===== TRACING: Could not discover functions after maximum retries =====")
            
        return available_functions

    @abstractmethod
    def process_request(self, request: Any) -> Dict[str, Any]:
        """Process the request and return reply data as a dictionary"""
        pass

    def on_request(self, replier):
        """Handle incoming requests"""
        samples = replier.take_requests()
        for request, info in samples:
            if request is None or info.state.instance_state != dds.InstanceState.ALIVE:
                continue
                
            logger.info(f"Received request: {request}")
            
            # Get reply data from concrete implementation
            reply_data = self.process_request(request)
            
            # Create reply
            reply = dds.DynamicData(self.reply_type)
            for key, value in reply_data.items():
                reply[key] = value
                
            # Send reply
            replier.send_reply(reply, info)
            logger.info(f"Sent reply: {reply}")

    def run(self):
        """Main agent loop"""
        try:
            # Announce presence
            self.app.announce_self()
            
            # Main loop - process requests
            logger.info(f"{self.agent_name} listening for requests (Ctrl+C to exit)...")
            while True:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info(f"\nShutting down {self.agent_name}...")
            self.replier.close()
            self.app.close()
            sys.exit(0)

    def close(self):
        """Clean up resources"""
        try:
            # Close replier
            if hasattr(self, 'replier') and not getattr(self.replier, '_closed', False):
                self.replier.close()
                
            # Close app
            if hasattr(self, 'app') and not getattr(self.app, '_closed', False):
                self.app.close()
                
            logger.info(f"GenesisAgent {self.agent_name} closed successfully")
        except Exception as e:
            logger.error(f"Error closing GenesisAgent: {str(e)}")
            logger.error(traceback.format_exc())

class GenesisAnthropicChatAgent(GenesisAgent, AnthropicChatAgent):
    """Genesis agent that uses Anthropic's Claude model"""
    def __init__(self, model_name: str = "claude-3-opus-20240229", api_key: Optional[str] = None,
                 system_prompt: Optional[str] = None, max_history: int = 10):
        GenesisAgent.__init__(self, "Claude", "Chat")
        AnthropicChatAgent.__init__(self, model_name, api_key, system_prompt, max_history)
        
    def process_request(self, request: Any) -> Dict[str, Any]:
        """Process chat request using Claude"""
        message = request["message"]
        conversation_id = request["conversation_id"]
        
        response, status = self.generate_response(message, conversation_id)
        
        return {
            "response": response,
            "status": status
        } 