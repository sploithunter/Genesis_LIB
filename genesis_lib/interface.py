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
        self.subscription_matched = False
        self._registration_event = asyncio.Event()
        logger.info("🔧 TRACE: Registration listener initialized")
        
    def on_data_available(self, reader):
        """Handle new registration announcements"""
        # print("🔔 IMMEDIATE PRINT: RegistrationListener.on_data_available called")  # Direct print for immediate feedback
        logger.info("🔔 IMMEDIATE LOG: RegistrationListener.on_data_available called")
        try:
            samples = reader.take()
            # print(f"📦 IMMEDIATE PRINT: Took {len(samples)} samples from reader")  # Direct print
            logger.info(f"📦 IMMEDIATE LOG: Took {len(samples)} samples from reader")
            
            for data, info in samples:
                if data is None or info.state.instance_state != dds.InstanceState.ALIVE:
                    logger.warning(f"⚠️ TRACE: Skipping sample - None or not alive. State: {info.state.instance_state if info else 'Unknown'}")
                    continue
                    
                instance_id = data['instance_id']
                logger.info("✨ TRACE: ====== REGISTRATION ANNOUNCEMENT RECEIVED ======")
                logger.info(f"✨ TRACE: Message: {data['message']}")
                logger.info(f"✨ TRACE: Preferred Name: {data['prefered_name']}")
                logger.info(f"✨ TRACE: Default Capable: {data['default_capable']}")
                logger.info(f"✨ TRACE: Instance ID: {data['instance_id']}")
                logger.info(f"✨ TRACE: Instance State: {info.state.instance_state}")
                logger.info("✨ TRACE: ============================================")
                
                self.received_announcements[instance_id] = {
                    'message': data['message'],
                    'prefered_name': data['prefered_name'],
                    'default_capable': data['default_capable'],
                    'instance_id': instance_id,
                    'timestamp': time.time()
                }
                self._registration_event.set()
        except Exception as e:
            logger.error(f"❌ TRACE: Error processing registration announcement: {e}")
            logger.error(traceback.format_exc())
                    
    def on_subscription_matched(self, reader, status):
        """Track when registration publishers are discovered"""
        logger.info(f"🤝 TRACE: Registration subscription matched event. Current count: {status.current_count}")
        self.subscription_matched = status.current_count > 0
        
        if status.current_count > 0:
            logger.info("✅ TRACE: Registration subscription successfully matched with publisher")
        else:
            logger.warning("⚠️ TRACE: Registration subscription lost all publisher matches")

class GenesisInterface(ABC):
    """Base class for all Genesis interfaces"""
    def __init__(self, interface_name: str, service_name: str):
        self.interface_name = interface_name
        self.service_name = service_name
        self.app = GenesisApp(preferred_name=interface_name)
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.request_type = self.type_provider.type("genesis_lib", f"{service_name}Request")
        self.reply_type = self.type_provider.type("genesis_lib", f"{service_name}Reply")
        
        # Store member names for later use
        self.reply_members = [member.name for member in self.reply_type.members()]
        
        # Create requester
        self.requester = rpc.Requester(
            request_type=self.request_type,
            reply_type=self.reply_type,
            participant=self.app.participant,
            service_name=self.service_name
        )
        
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
        """Wait for agent to be discovered"""
        start_time = time.time()
        
        # Wait for registration listener to be ready
        while not hasattr(self, 'registration_listener'):
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for registration listener to be ready")
                return False
            await asyncio.sleep(0.1)
            
        try:
            # Wait for either registration announcement or RPC discovery
            logger.info("⏳ TRACE: Waiting directly for registration event or RPC match...")
            registration_task = asyncio.create_task(
                asyncio.wait_for(
                    self.registration_listener._registration_event.wait(),
                    timeout=timeout_seconds
                )
            )
            
            rpc_discovery_task = asyncio.create_task(
                self._wait_for_rpc_match()
            )
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [registration_task, rpc_discovery_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout_seconds
            )
            
            # Cancel pending task
            for task in pending:
                task.cancel()
                
            # Check which path succeeded
            if registration_task in done:
                logger.info("✅ TRACE: Found registration announcement while waiting for agent")
                return True
            elif rpc_discovery_task in done:
                logger.warning("⚠️ TRACE: Agent discovered through RPC, not through registration announcement")
                return True
            else:
                logger.error(f"Timeout waiting for {self.service_name} agent")
                return False
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for {self.service_name} agent")
            return False
            
    async def _wait_for_rpc_match(self):
        """Helper to wait for RPC discovery"""
        while self.requester.matched_replier_count == 0:
            await asyncio.sleep(0.1)
        logger.info(f"Found {self.service_name} agent through RPC!")

    async def send_request(self, request_data: Dict[str, Any], timeout_seconds: float = 10.0) -> Optional[Dict[str, Any]]:
        """Send request to agent and wait for reply"""
        try:
            # Create request
            request = dds.DynamicData(self.request_type)
            for key, value in request_data.items():
                request[key] = value
                
            # Send request and wait for reply using synchronous API in a thread
            logger.info(f"Sending request to agent: {request_data}")
            
            def _send_request_sync(req, timeout):
                request_id = self.requester.send_request(req)
                # Convert float seconds to int seconds and nanoseconds
                seconds = int(timeout)
                nanoseconds = int((timeout - seconds) * 1e9)
                replies = self.requester.receive_replies(
                    max_wait=dds.Duration(seconds=seconds, nanoseconds=nanoseconds),
                    min_count=1,
                    related_request_id=request_id
                )
                if replies:
                    return replies[0]  # Returns (reply, info) tuple
                return None
                
            result = await asyncio.to_thread(_send_request_sync, request, timeout_seconds)
            
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
        if hasattr(self, 'requester'):
            self.requester.close()
        if hasattr(self, 'app'):
            await self.app.close() 