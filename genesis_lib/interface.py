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
from genesis_lib.utils import get_datamodel_path
import asyncio
import traceback

# Get logger
logger = logging.getLogger(__name__)

class RegistrationListener(dds.DynamicData.NoOpDataReaderListener):
    """Listener for registration announcements"""
    def __init__(self, interface):
        logger.info("🔧 TRACE: RegistrationListener class init calling now")
        super().__init__()
        self.interface = interface
        self.received_announcements = {}  # Track announcements by instance_id
        self._registration_event = asyncio.Event()
        logger.info("🔧 TRACE: Registration listener initialized")
        
    def on_data_available(self, reader):
        """Handle new registration announcements"""
        logger.info("🔔 TRACE: RegistrationListener.on_data_available called")
        try:
            samples = reader.read()
            logger.info(f"📦 TRACE: Read {len(samples)} samples from reader")
            
            for data, info in samples:
                if data is None or info.state.instance_state != dds.InstanceState.ALIVE:
                    logger.warning(f"⚠️ TRACE: Skipping sample - None or not alive. State: {info.state.instance_state if info else 'Unknown'}")
                    continue
                    
                instance_id = data['instance_id']
                service_name = data['service_name'] # Extract service name
                logger.info("✨ TRACE: ====== REGISTRATION ANNOUNCEMENT RECEIVED ======")
                logger.info(f"✨ TRACE: Message: {data['message']}")
                logger.info(f"✨ TRACE: Preferred Name: {data['prefered_name']}")
                logger.info(f"✨ TRACE: Default Capable: {data['default_capable']}")
                logger.info(f"✨ TRACE: Instance ID: {data['instance_id']}")
                logger.info(f"✨ TRACE: Service Name: {service_name}") # Log service name
                logger.info(f"✨ TRACE: Instance State: {info.state.instance_state}")
                logger.info("✨ TRACE: ============================================")
                
                self.received_announcements[instance_id] = {
                    'message': data['message'],
                    'prefered_name': data['prefered_name'],
                    'default_capable': data['default_capable'],
                    'instance_id': instance_id,
                    'service_name': service_name, # Store service name
                    'timestamp': time.time()
                }
                self._registration_event.set()
                logger.info("✅ TRACE: Registration event set")
        except Exception as e:
            logger.error(f"❌ TRACE: Error processing registration announcement: {e}")
            logger.error(traceback.format_exc())

    def on_subscription_matched(self, reader, status):
        """Track when registration publishers are discovered"""
        logger.info(f"🤝 TRACE: Registration subscription matched event. Current count: {status.current_count}")
        # We're not using this for discovery anymore, just logging for debugging

class GenesisInterface(ABC):
    """Base class for all Genesis interfaces"""
    def __init__(self, interface_name: str, service_name: str):
        self.interface_name = interface_name
        self.service_name = service_name # This is the *interface's* service name, may differ from agent's
        self.app = GenesisApp(preferred_name=interface_name)
        self.discovered_agent_service_name: Optional[str] = None # To store discovered agent service name
        self.requester: Optional[rpc.Requester] = None # Requester will be created after discovery
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        # Hardcode ChatGPT request/reply types
        self.request_type = self.type_provider.type("genesis_lib", "ChatGPTRequest")
        self.reply_type = self.type_provider.type("genesis_lib", "ChatGPTReply")
        
        # Store member names for later use
        self.reply_members = [member.name for member in self.reply_type.members()]
        
        # Set up registration monitoring with listener
        self._setup_registration_monitoring()

    def _setup_registration_monitoring(self):
        """Set up registration monitoring with listener"""
        try:
            logger.info("🔧 TRACE: Setting up registration monitoring...")
            
            # Configure reader QoS
            reader_qos = dds.QosProvider.default.datareader_qos
            reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
            reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
            reader_qos.history.kind = dds.HistoryKind.KEEP_LAST
            reader_qos.history.depth = 500  # Match agent's writer depth
            reader_qos.liveliness.kind = dds.LivelinessKind.AUTOMATIC
            reader_qos.liveliness.lease_duration = dds.Duration(seconds=2)
            reader_qos.ownership.kind = dds.OwnershipKind.SHARED
            
            logger.info("📋 TRACE: Configured reader QoS settings")
            
            # Create registration reader with listener
            logger.info("🎯 TRACE: Creating registration listener...")
            self.registration_listener = RegistrationListener(self)
            
            logger.info("📡 TRACE: Creating registration reader...")
            self.app.registration_reader = dds.DynamicData.DataReader(
                subscriber=self.app.subscriber,
                topic=self.app.registration_topic,
                qos=reader_qos,
                listener=self.registration_listener,
                mask=dds.StatusMask.DATA_AVAILABLE | dds.StatusMask.SUBSCRIPTION_MATCHED
            )
            # print(f"🔍 IMMEDIATE PRINT: Listener attached to reader: {id(self.app.registration_reader.listener)}")
            # print(f"🔍 IMMEDIATE PRINT: Listener instance variable: {id(self.registration_listener)}")
            
            logger.info("✅ TRACE: Registration monitoring setup complete")
            
        except Exception as e:
            logger.error(f"❌ TRACE: Error setting up registration monitoring: {e}")
            logger.error(traceback.format_exc())
            raise

    async def wait_for_agent(self, timeout_seconds: int = 30) -> bool:
        """Wait for agent to be discovered, store its service name, and create requester."""
        logger.info("Starting agent discovery wait")
        logger.debug("Interface DDS Domain ID from env: %s", os.getenv('ROS_DOMAIN_ID', 'Not Set'))
        logger.debug("Interface service name: %s", self.service_name)
        
        # Log participant info if available
        if hasattr(self.app, 'participant'):
            logger.debug("Interface DDS participant initialized")
            logger.debug("Interface DDS domain ID: %d", self.app.participant.domain_id)
        else:
            logger.warning("Interface participant not initialized")
            
        start_time = time.time()
        
        # Wait for registration listener to be ready
        while not hasattr(self, 'registration_listener'):
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for registration listener to be ready")
                return False
            await asyncio.sleep(0.1)
            
        discovered_service_name = None
        try:
            # First check if there are any registration announcements in the queue
            logger.info("🔍 TRACE: Checking registration queue for existing announcements...")
            samples = self.app.registration_reader.read()
            if samples:
                logger.info(f"📦 TRACE: Found {len(samples)} registration announcements in queue")
                for data, info in samples:
                    if data is not None and info.state.instance_state == dds.InstanceState.ALIVE:
                        service_name = data['service_name']
                        logger.info("✨ TRACE: ====== FOUND EXISTING REGISTRATION ANNOUNCEMENT ======")
                        logger.info(f"✨ TRACE: Message: {data['message']}")
                        logger.info(f"✨ TRACE: Preferred Name: {data['prefered_name']}")
                        logger.info(f"✨ TRACE: Service Name: {service_name}")
                        logger.info(f"✨ TRACE: Instance ID: {data['instance_id']}")
                        logger.info("✨ TRACE: ============================================")
                        discovered_service_name = service_name
                        break # Take the first one found in the queue
            
            # If no existing announcements, wait for registration event
            if not discovered_service_name:
                logger.info("⏳ TRACE: No existing announcements, waiting for registration event...")
                try:
                    await asyncio.wait_for(
                        self.registration_listener._registration_event.wait(),
                        timeout=timeout_seconds
                    )
                    # Event triggered, find the service name from the listener's cache
                    if self.registration_listener.received_announcements:
                         # Get the latest announcement based on timestamp or just the last added one
                         latest_announcement = list(self.registration_listener.received_announcements.values())[-1]
                         discovered_service_name = latest_announcement.get('service_name')
                         logger.info(f"✅ TRACE: Found registration announcement via event. Service Name: {discovered_service_name}")
                    else:
                         logger.warning("⚠️ TRACE: Registration event triggered but no announcements found in listener cache.")

                except asyncio.TimeoutError:
                    logger.error(f"Timeout waiting for registration event for agent")
                    return False

            # If we discovered a service name, store it and create the requester
            if discovered_service_name:
                self.discovered_agent_service_name = discovered_service_name
                logger.info(f"✅ TRACE: Agent discovered with service name: {self.discovered_agent_service_name}")
                
                # Create the requester using the discovered agent's service name
                try:
                    self.requester = rpc.Requester(
                        request_type=self.request_type,
                        reply_type=self.reply_type,
                        participant=self.app.participant,
                        service_name=self.discovered_agent_service_name # USE DISCOVERED NAME
                    )
                    logger.info(f"✅ TRACE: RPC Requester created for service: {self.discovered_agent_service_name}")
                    return True
                except Exception as req_e:
                    logger.error(f"❌ TRACE: Failed to create RPC Requester for service {self.discovered_agent_service_name}: {req_e}")
                    logger.error(traceback.format_exc())
                    return False
            else:
                logger.error("❌ TRACE: Failed to discover agent service name after waiting.")
                return False
                
        except Exception as e:
            logger.error(f"Error waiting for agent: {e}")
            logger.error(traceback.format_exc())
            return False
            
    async def _wait_for_rpc_match(self):
        """Helper to wait for RPC discovery"""
        # This might need adjustment or removal if we rely solely on registration discovery now
        if not self.requester:
             logger.warning("⚠️ TRACE: Requester not created yet, cannot wait for RPC match.")
             return
        while self.requester.matched_replier_count == 0:
            await asyncio.sleep(0.1)
        logger.info(f"RPC match confirmed for service: {self.discovered_agent_service_name}!")

    async def send_request(self, request_data: Dict[str, Any], timeout_seconds: float = 10.0) -> Optional[Dict[str, Any]]:
        """Send request to agent and wait for reply"""
        if not self.requester:
            logger.error("❌ TRACE: Cannot send request, agent not discovered or requester not created.")
            return None
            
        try:
            # Create request
            request = dds.DynamicData(self.request_type)
            for key, value in request_data.items():
                request[key] = value
                
            # Send request and wait for reply using synchronous API in a thread
            logger.info(f"Sending request to agent service '{self.discovered_agent_service_name}': {request_data}")
            
            def _send_request_sync(requester, req, timeout):
                # Ensure the requester is valid before using it
                if requester is None:
                    logger.error("❌ TRACE: _send_request_sync called with None requester.")
                    return None
                try:
                    request_id = requester.send_request(req)
                    # Convert float seconds to int seconds and nanoseconds
                    seconds = int(timeout)
                    nanoseconds = int((timeout - seconds) * 1e9)
                    replies = requester.receive_replies(
                        max_wait=dds.Duration(seconds=seconds, nanoseconds=nanoseconds),
                        min_count=1,
                        related_request_id=request_id
                    )
                    if replies:
                        return replies[0]  # Returns (reply, info) tuple
                    return None
                except Exception as sync_e:
                    logger.error(f"❌ TRACE: Error in _send_request_sync: {sync_e}")
                    logger.error(traceback.format_exc())
                    return None
                
            result = await asyncio.to_thread(_send_request_sync, self.requester, request, timeout_seconds)
            
            if result:
                reply, info = result
                # Convert reply to dict
                reply_dict = {}
                for member in self.reply_members:
                    reply_dict[member] = reply[member]
                    
                logger.info(f"Received reply from agent: {reply_dict}")
                return reply_dict
            else:
                logger.error("No reply received")
                return None
            
        except dds.TimeoutError:
            logger.error(f"Timeout waiting for reply after {timeout_seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            return None

    async def close(self):
        """Clean up resources"""
        if hasattr(self, 'requester') and self.requester: # Check if requester exists before closing
            self.requester.close()
        if hasattr(self, 'app'):
            await self.app.close() 