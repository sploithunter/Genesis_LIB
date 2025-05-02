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

# Get logger
logger = logging.getLogger(__name__)

class RegistrationListener(dds.DynamicData.NoOpDataReaderListener):
    """Listener for registration announcements"""
    def __init__(self, interface):
        super().__init__()
        self.interface = interface
        self.received_announcements = {}  # Track announcements by instance_id
        self.subscription_matched = False
        
    def on_data_available(self, reader):
        """Handle new registration announcements"""
        try:
            samples = reader.take()
            for sample, info in samples:
                if sample is not None and info.valid:
                    instance_id = sample['instance_id']
                    self.received_announcements[instance_id] = {
                        'message': sample['message'],
                        'prefered_name': sample['prefered_name'],
                        'default_capable': sample['default_capable'],
                        'instance_id': instance_id,
                        'timestamp': time.time()
                    }
                    logger.info("🔔 TRACE: Received registration announcement:")
                    logger.info(f"   Message: {sample['message']}")
                    logger.info(f"   Preferred Name: {sample['prefered_name']}")
                    logger.info(f"   Default Capable: {sample['default_capable']}")
                    logger.info(f"   Instance ID: {sample['instance_id']}")
        except Exception as e:
            logger.error(f"Error processing registration announcement: {e}")
                    
    def on_subscription_matched(self, reader, status):
        """Track when registration publishers are discovered"""
        logger.info(f"Registration subscription matched. Current count: {status.current_count}")
        self.subscription_matched = status.current_count > 0

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
        # Configure reader QoS
        reader_qos = dds.QosProvider.default.datareader_qos
        reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        reader_qos.history.kind = dds.HistoryKind.KEEP_LAST
        reader_qos.history.depth = 500  # Match agent's writer depth
        reader_qos.liveliness.kind = dds.LivelinessKind.AUTOMATIC
        reader_qos.liveliness.lease_duration = dds.Duration(seconds=2)
        reader_qos.ownership.kind = dds.OwnershipKind.SHARED
        
        # Create registration reader with listener
        self.registration_listener = RegistrationListener(self)
        self.app.registration_reader = dds.DynamicData.DataReader(
            subscriber=self.app.subscriber,
            topic=self.app.registration_topic,
            qos=reader_qos,
            listener=self.registration_listener,
            mask=dds.StatusMask.DATA_AVAILABLE | dds.StatusMask.SUBSCRIPTION_MATCHED
        )
        
        logger.info("Registration monitoring setup complete")

    async def wait_for_agent(self, timeout_seconds: int = 30) -> bool:
        """Wait for agent to be discovered"""
        start_time = time.time()
        
        # Wait for registration listener to be ready
        while not hasattr(self, 'registration_listener'):
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for registration listener to be ready")
                return False
            await asyncio.sleep(0.1)
            
        # Wait for subscription to be matched
        while not self.registration_listener.subscription_matched:
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for registration subscription to be matched")
                return False
            await asyncio.sleep(0.1)
            
        while self.requester.matched_replier_count == 0:
            # Check if we've received any registration announcements
            if self.registration_listener.received_announcements:
                logger.info("✅ TRACE: Found registration announcement while waiting for agent")
                return True
                
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Timeout waiting for {self.service_name} agent")
                return False
                
            logger.info(f"Waiting for {self.service_name} agent to appear...")
            await asyncio.sleep(1)
            
        logger.info(f"Found {self.service_name} agent!")
        
        # If we got here through RPC discovery but didn't see a registration announcement, warn
        if not self.registration_listener.received_announcements:
            logger.warning("⚠️ TRACE: Agent discovered through RPC, not through registration announcement")
        
        return True

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