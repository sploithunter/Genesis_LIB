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
        
        # Create event loop for async operations
        self.loop = asyncio.get_event_loop()
        
        # Create replier with data available listener
        class RequestListener(dds.DynamicData.DataReaderListener):
            def __init__(self, agent):
                super().__init__()  # Call parent class __init__
                self.agent = agent
                
            def on_data_available(self, reader):
                # Get all available samples
                samples = self.agent.replier.take_requests()
                for request, info in samples:
                    if request is None or info.state.instance_state != dds.InstanceState.ALIVE:
                        continue
                        
                    logger.info(f"Received request: {request}")
                    
                    try:
                        # Create task to process request asynchronously
                        asyncio.run_coroutine_threadsafe(self._process_request(request, info), self.agent.loop)
                    except Exception as e:
                        logger.error(f"Error creating request processing task: {e}")
                        logger.error(traceback.format_exc())
                        
            async def _process_request(self, request, info):
                try:
                    # Get reply data from concrete implementation
                    reply_data = await self.agent.process_request(request)
                    
                    # Create reply
                    reply = dds.DynamicData(self.agent.reply_type)
                    for key, value in reply_data.items():
                        reply[key] = value
                        
                    # Send reply
                    self.agent.replier.send_reply(reply, info)
                    logger.info(f"Sent reply: {reply}")
                except Exception as e:
                    logger.error(f"Error processing request: {e}")
                    logger.error(traceback.format_exc())
                    # Send error reply
                    reply = dds.DynamicData(self.agent.reply_type)
                    reply["status"] = 1  # Error status
                    reply["message"] = f"Error: {str(e)}"
                    self.agent.replier.send_reply(reply, info)
        
        # Create replier with listener
        self.replier = rpc.Replier(
            request_type=self.request_type,
            reply_type=self.reply_type,
            participant=self.app.participant,
            service_name=self.service_name
        )
        
        # Set listener on replier's DataReader with status mask for data available
        self.request_listener = RequestListener(self)
        mask = dds.StatusMask.DATA_AVAILABLE
        self.replier.request_datareader.set_listener(self.request_listener, mask)
        
        # Store discovered functions
        self.discovered_functions = []

    @abstractmethod
    async def process_request(self, request: Any) -> Dict[str, Any]:
        """Process the request and return reply data as a dictionary"""
        pass

    async def discover_functions(self, function_client, max_retries: int = 5) -> List[Dict[str, Any]]:
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
                # Discover functions using the client
                logger.info("===== TRACING: Calling discover_functions on function client =====")
                await function_client.discover_functions()
                
                # Get the list of available functions
                available_functions = function_client.list_available_functions()
                
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
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"===== TRACING: Error discovering functions: {str(e)} =====")
                logger.error(traceback.format_exc())
                retry_count += 1
                await asyncio.sleep(1)
                
        if retry_count >= max_retries:
            logger.warning("===== TRACING: Could not discover functions after maximum retries =====")
            
        return available_functions

    async def run(self):
        """Main agent loop"""
        try:
            # Announce presence
            logger.info("Announcing agent presence...")
            await self.app.announce_self()
            
            # Main loop - just keep the event loop running
            logger.info(f"{self.agent_name} listening for requests (Ctrl+C to exit)...")
            shutdown_event = asyncio.Event()
            await shutdown_event.wait()
                
        except KeyboardInterrupt:
            logger.info(f"\nShutting down {self.agent_name}...")
            await self.close()
            sys.exit(0)

    async def close(self):
        """Clean up resources"""
        try:
            # Close replier first
            if hasattr(self, 'replier') and not getattr(self.replier, '_closed', False):
                self.replier.close()
                
            # Close app last since it handles registration
            if hasattr(self, 'app') and self.app is not None and not getattr(self.app, '_closed', False):
                await self.app.close()
                
            logger.info(f"GenesisAgent {self.agent_name} closed successfully")
        except Exception as e:
            logger.error(f"Error closing GenesisAgent: {str(e)}")
            logger.error(traceback.format_exc())

    # Sync version of close for backward compatibility
    def close_sync(self):
        """Synchronous version of close for backward compatibility"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.close())
        finally:
            loop.close()

class GenesisAnthropicChatAgent(GenesisAgent, AnthropicChatAgent):
    """Genesis agent that uses Anthropic's Claude model"""
    def __init__(self, model_name: str = "claude-3-opus-20240229", api_key: Optional[str] = None,
                 system_prompt: Optional[str] = None, max_history: int = 10):
        GenesisAgent.__init__(self, "Claude", "Chat")
        AnthropicChatAgent.__init__(self, model_name, api_key, system_prompt, max_history)
        
    async def process_request(self, request: Any) -> Dict[str, Any]:
        """Process chat request using Claude"""
        message = request["message"]
        conversation_id = request["conversation_id"]
        
        response, status = await self.generate_response(message, conversation_id)
        
        return {
            "response": response,
            "status": status
        } 