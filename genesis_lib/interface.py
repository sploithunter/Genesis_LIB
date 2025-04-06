"""
Base interface class for the GENESIS library.
"""

import time
import logging
import os
from abc import ABC
from typing import Any, Dict, Optional, List
import rti.connextdds as dds
import rti.rpc as rpc
from .genesis_app import GenesisApp
import uuid
import json
from genesis_lib.utils import get_datamodel_path, load_datamodel
from genesis_lib.datamodel import FunctionRequest, FunctionReply

# Get logger
logger = logging.getLogger(__name__)

class GenesisInterface(ABC):
    """Base class for all Genesis interfaces"""
    def __init__(self, interface_name: str, service_name: str):
        self.interface_name = interface_name
        self.service_name = service_name
        self.app = GenesisApp(preferred_name=interface_name)
        
        # Use IDL-based types directly for RPC
        self.request_type = FunctionRequest
        self.reply_type = FunctionReply
        
        # Store member names for later use
        self.reply_members = ["result_json", "success", "error_message"]
        
        # Create requester
        self.requester = rpc.Requester(
            request_type=self.request_type,
            reply_type=self.reply_type,
            participant=self.app.participant,
            service_name=self.service_name
        )

    def wait_for_agent(self, timeout_seconds: int = 30) -> bool:
        """Wait for agent to be discovered"""
        start_time = time.time()
        while self.requester.matched_replier_count == 0:
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for {self.service_name} agent")
                return False
            logger.info(f"Waiting for {self.service_name} agent to appear...")
            time.sleep(1)
        logger.info(f"Found {self.service_name} agent!")
        
        # Store agent info when discovered
        if self.requester.matched_replier_count > 0:
            # Get the DDS participant GUIDs
            provider_id = str(self.app.participant.instance_handle)  # Interface's GUID
            
            # Get the replier's GUID
            replier_guids = self.requester.reply_datareader.matched_publications
            first_replier_guid = replier_guids[0]
            client_id = str(first_replier_guid)
            
            agent_id = str(uuid.uuid4())
            
            self.agent_info = {
                'instance_handle': provider_id,
                'service_name': self.service_name,
                'agent_id': agent_id
            }
            
            # Format the reason string with correct provider/client IDs
            reason = f"provider={provider_id} client={client_id} agent={agent_id} name={self.service_name}"
            logger.info(f"Publishing edge discovery event with reason: {reason}")
            
            # Let the monitored interface handle publishing the event
            if hasattr(self, 'publish_component_lifecycle_event'):
                self.publish_component_lifecycle_event(
                    previous_state="DISCOVERING",
                    new_state="DISCOVERING",
                    reason=reason,
                    capabilities=json.dumps({
                        "agent_type": "INTERFACE",
                        "service": self.service_name,
                        "edge_type": "agent_connection",
                        "entity_type": "AGENT",
                        "component_type": "AGENT",
                        "provider_id": provider_id,
                        "client_id": client_id,
                        "agent_id": agent_id
                    }),
                    event_category="EDGE_DISCOVERY",
                    source_id=client_id,
                    target_id=provider_id,
                    connection_type="agent_connection"
                )
            
            return True
        
        return False

    def send_request(self, request_data: Dict[str, Any], timeout_seconds: int = 15) -> Optional[Any]:
        """Send request to agent and wait for reply"""
        try:
            # Create request using IDL type
            request = FunctionRequest()
            request.id = str(uuid.uuid4())
            request.type = "function"
            request.function.name = request_data.get("function_name", "")
            request.function.arguments = json.dumps(request_data.get("parameters", {}))
                
            # Send request and wait for reply
            logger.info(f"Sending request: {request}")
            request_id = self.requester.send_request(request)
            
            # Wait for reply with timeout
            try:
                replies = self.requester.receive_replies(
                    max_wait=dds.Duration(seconds=timeout_seconds),
                    min_count=1,
                    related_request_id=request_id
                )
                
                if replies:
                    reply, info = replies[0]  # Get first reply
                    logger.info(f"Received reply: {reply}")
                    return {
                        "result": json.loads(reply.result_json) if reply.success else None,
                        "success": reply.success,
                        "error_message": reply.error_message
                    }
                    
                logger.error("No reply received")
                return None
                
            except dds.TimeoutError:
                logger.error("Timeout waiting for reply")
                return None
            
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            return None

    def close(self):
        """Clean up resources"""
        if hasattr(self, 'requester'):
            self.requester.close()
        if hasattr(self, 'app'):
            self.app.close() 