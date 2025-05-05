"""
Base interface class for the GENESIS library.
"""

import time
import logging
import os
from abc import ABC
from typing import Any, Dict, Optional, List, Callable, Coroutine
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
    def __init__(self, 
                 interface, 
                 loop: asyncio.AbstractEventLoop,
                 on_discovered: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None, 
                 on_departed: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None):
        logger.info("🔧 TRACE: RegistrationListener class init calling now")
        super().__init__()
        self.interface = interface
        self.received_announcements = {}  # Track announcements by instance_id
        self.on_agent_discovered = on_discovered
        self.on_agent_departed = on_departed
        self._loop = loop
        logger.info("🔧 TRACE: Registration listener initialized with callbacks")
        
    def on_data_available(self, reader):
        """Handle new registration announcements and departures"""
        logger.info("🔔 TRACE: RegistrationListener.on_data_available called (sync)")
        try:
            samples = reader.take()
            logger.info(f"📦 TRACE: Took {len(samples)} samples from reader")
            
            for data, info in samples:
                if data is None:
                    logger.warning(f"⚠️ TRACE: Skipping sample - data is None. Instance Handle: {info.instance_handle if info else 'Unknown'}")
                    continue
                    
                instance_id = data.get_string('instance_id')
                if not instance_id:
                    logger.warning(f"⚠️ TRACE: Skipping sample - missing instance_id. Data: {data}")
                    continue

                if info.state.instance_state == dds.InstanceState.ALIVE:
                    if instance_id not in self.received_announcements:
                        service_name = data.get_string('service_name')
                        prefered_name = data.get_string('prefered_name')
                        agent_info = {
                            'message': data.get_string('message'),
                            'prefered_name': prefered_name,
                            'default_capable': data.get_int32('default_capable'),
                            'instance_id': instance_id,
                            'service_name': service_name,
                            'timestamp': time.time()
                        }
                        self.received_announcements[instance_id] = agent_info
                        logger.info(f"✨ TRACE: Agent DISCOVERED: {prefered_name} ({service_name}) - ID: {instance_id}")
                        if self.on_agent_discovered:
                            # Schedule the async task creation onto the main loop thread
                            self._loop.call_soon_threadsafe(asyncio.create_task, self._run_discovery_callback(agent_info))
                elif info.state.instance_state in [dds.InstanceState.NOT_ALIVE_DISPOSED, dds.InstanceState.NOT_ALIVE_NO_WRITERS]:
                    if instance_id in self.received_announcements:
                        departed_info = self.received_announcements.pop(instance_id)
                        logger.info(f"👻 TRACE: Agent DEPARTED: {departed_info.get('prefered_name', 'N/A')} - ID: {instance_id} - Reason: {info.state.instance_state}")
                        if self.on_agent_departed:
                            # Schedule the async task creation onto the main loop thread
                            self._loop.call_soon_threadsafe(asyncio.create_task, self._run_departure_callback(instance_id))
        except dds.Error as dds_e:
            logger.error(f"❌ TRACE: DDS Error in on_data_available: {dds_e}")
            logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"❌ TRACE: Unexpected error processing registration announcement: {e}")
            logger.error(traceback.format_exc())

    def on_subscription_matched(self, reader, status):
        """Track when registration publishers are discovered"""
        logger.info(f"🤝 TRACE: Registration subscription matched event. Current count: {status.current_count}")
        # We're not using this for discovery anymore, just logging for debugging

    # --- Helper methods to run async callbacks --- 
    async def _run_discovery_callback(self, agent_info: Dict[str, Any]):
        """Safely run the discovery callback coroutine."""
        try:
            # Check again in case the callback was unset between scheduling and running
            if self.on_agent_discovered: 
                await self.on_agent_discovered(agent_info)
        except Exception as cb_e:
            instance_id = agent_info.get('instance_id', 'UNKNOWN')
            logger.error(f"❌ TRACE: Error executing on_agent_discovered callback task for {instance_id}: {cb_e}")
            logger.error(traceback.format_exc())
            
    async def _run_departure_callback(self, instance_id: str):
        """Safely run the departure callback coroutine."""
        try:
            # Check again
            if self.on_agent_departed:
                await self.on_agent_departed(instance_id)
        except Exception as cb_e:
            logger.error(f"❌ TRACE: Error executing on_agent_departed callback task for {instance_id}: {cb_e}")
            logger.error(traceback.format_exc())
    # --- End helper methods --- 

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
        
        # Placeholders for callbacks
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_agent_discovered_callback: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None
        self._on_agent_departed_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
        
        # Set up registration monitoring with listener
        self._loop = asyncio.get_running_loop()
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
            self.registration_listener = RegistrationListener(
                self,
                self._loop,
                on_discovered=self._on_agent_discovered_callback, 
                on_departed=self._on_agent_departed_callback
            )
            
            logger.info("📡 TRACE: Creating registration reader...")
            self.app.registration_reader = dds.DynamicData.DataReader(
                subscriber=self.app.subscriber,
                topic=self.app.registration_topic,
                qos=reader_qos,
                listener=self.registration_listener,
                mask=dds.StatusMask.DATA_AVAILABLE | dds.StatusMask.SUBSCRIPTION_MATCHED
            )
            
            logger.info("✅ TRACE: Registration monitoring setup complete")
            
        except Exception as e:
            logger.error(f"❌ TRACE: Error setting up registration monitoring: {e}")
            logger.error(traceback.format_exc())
            raise

    async def connect_to_agent(self, service_name: str, timeout_seconds: float = 5.0) -> bool:
        """
        Create the RPC Requester to connect to a specific agent service.
        Waits briefly for the underlying DDS replier endpoint to be matched.
        """
        if self.requester:
             logger.warning(f"⚠️ TRACE: Requester already exists for service '{self.discovered_agent_service_name}'. Overwriting.")
             self.requester.close()

        logger.info(f"🔗 TRACE: Attempting to connect to agent service: {service_name}")
        try:
            self.requester = rpc.Requester(
                request_type=self.request_type,
                reply_type=self.reply_type,
                participant=self.app.participant,
                service_name=service_name
            )
            self.discovered_agent_service_name = service_name

            start_time = time.time()
            while self.requester.matched_replier_count == 0:
                if time.time() - start_time > timeout_seconds:
                    logger.error(f"❌ TRACE: Timeout ({timeout_seconds}s) waiting for DDS replier match for service '{service_name}'")
                    self.requester.close()
                    self.requester = None
                    self.discovered_agent_service_name = None
                    return False
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ TRACE: RPC Requester created and DDS replier matched for service: {service_name}")
            return True
            
        except Exception as req_e:
            logger.error(f"❌ TRACE: Failed to create or match RPC Requester for service '{service_name}': {req_e}")
            logger.error(traceback.format_exc())
            self.requester = None
            self.discovered_agent_service_name = None
            return False

    async def _wait_for_rpc_match(self):
        """Helper to wait for RPC discovery"""
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

    # --- New Callback Registration Methods ---
    def register_discovery_callback(self, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]):
        """Register a callback to be invoked when an agent is discovered."""
        logger.info(f"🔧 TRACE: Registering discovery callback: {callback.__name__ if callback else 'None'}")
        self._on_agent_discovered_callback = callback
        # If listener already exists, update its callback directly
        if hasattr(self, 'registration_listener') and self.registration_listener:
            self.registration_listener.on_agent_discovered = callback

    def register_departure_callback(self, callback: Callable[[str], Coroutine[Any, Any, None]]):
        """Register a callback to be invoked when an agent departs."""
        logger.info(f"🔧 TRACE: Registering departure callback: {callback.__name__ if callback else 'None'}")
        self._on_agent_departed_callback = callback
        # If listener already exists, update its callback directly
        if hasattr(self, 'registration_listener') and self.registration_listener:
            self.registration_listener.on_agent_departed = callback
    # --- End New Callback Registration Methods --- 