#!/usr/bin/env python3
"""
Monitored interface base class for the GENESIS library.
Provides monitoring capabilities for all interfaces.
"""

import logging
import time
import uuid
import json
import os
from typing import Any, Dict, Optional
import rti.connextdds as dds
from .interface import GenesisInterface
from genesis_lib.utils import get_datamodel_path
import asyncio

# Configure logging
logger = logging.getLogger(__name__)

# Event type mapping
EVENT_TYPE_MAP = {
    "INTERFACE_DISCOVERY": 0,  # Legacy discovery event
    "INTERFACE_REQUEST": 1,    # Request event
    "INTERFACE_RESPONSE": 2,   # Response event
    "INTERFACE_STATUS": 3      # Status event
}

class MonitoredInterface(GenesisInterface):
    """
    Base class for interfaces with monitoring capabilities.
    Extends GenesisInterface to add standardized monitoring.
    """
    
    def __init__(self, interface_name: str, service_name: str):
        """
        Initialize the monitored interface.
        
        Args:
            interface_name: Name of the interface
            service_name: Name of the service this interface connects to
        """
        super().__init__(interface_name=interface_name, service_name=service_name)
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.request_type = self.type_provider.type("genesis_lib", f"{service_name}Request")
        self.reply_type = self.type_provider.type("genesis_lib", f"{service_name}Reply")
        
        # Set up monitoring
        self._setup_monitoring()
        
        # Announce interface presence
        self._publish_discovery_event()
        
        logger.info(f"Monitored interface {interface_name} initialized")
    
    def _setup_monitoring(self):
        """Set up DDS entities for monitoring"""
        # Get monitoring type from XML
        self.monitoring_type = self.type_provider.type("genesis_lib", "MonitoringEvent")
        
        # Create monitoring topic
        self.monitoring_topic = dds.DynamicData.Topic(
            self.app.participant,
            "MonitoringEvent",
            self.monitoring_type
        )
        
        # Create monitoring publisher with QoS
        publisher_qos = dds.QosProvider.default.publisher_qos
        publisher_qos.partition.name = [""]  # Default partition
        self.monitoring_publisher = dds.Publisher(
            participant=self.app.participant,
            qos=publisher_qos
        )
        
        # Create monitoring writer with QoS
        writer_qos = dds.QosProvider.default.datawriter_qos
        writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        self.monitoring_writer = dds.DynamicData.DataWriter(
            pub=self.monitoring_publisher,
            topic=self.monitoring_topic,
            qos=writer_qos
        )

        # Set up enhanced monitoring (V2)
        # Create topics for new monitoring types
        self.component_lifecycle_type = self.type_provider.type("genesis_lib", "ComponentLifecycleEvent")
        self.chain_event_type = self.type_provider.type("genesis_lib", "ChainEvent")
        self.liveliness_type = self.type_provider.type("genesis_lib", "LivelinessUpdate")

        # Create topics
        self.component_lifecycle_topic = dds.DynamicData.Topic(
            self.app.participant,
            "ComponentLifecycleEvent",
            self.component_lifecycle_type
        )
        self.chain_event_topic = dds.DynamicData.Topic(
            self.app.participant,
            "ChainEvent",
            self.chain_event_type
        )
        self.liveliness_topic = dds.DynamicData.Topic(
            self.app.participant,
            "LivelinessUpdate",
            self.liveliness_type
        )

        # Create writers with QoS
        writer_qos = dds.QosProvider.default.datawriter_qos
        writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE

        # Create writers for each monitoring type
        self.component_lifecycle_writer = dds.DynamicData.DataWriter(
            pub=self.monitoring_publisher,
            topic=self.component_lifecycle_topic,
            qos=writer_qos
        )
        self.chain_event_writer = dds.DynamicData.DataWriter(
            pub=self.monitoring_publisher,
            topic=self.chain_event_topic,
            qos=writer_qos
        )
        self.liveliness_writer = dds.DynamicData.DataWriter(
            pub=self.monitoring_publisher,
            topic=self.liveliness_topic,
            qos=writer_qos
        )
    
    def _publish_discovery_event(self):
        """Publish interface discovery event"""
        interface_id = str(self.app.participant.instance_handle)
        
        # First publish node discovery event for the interface itself
        self.publish_component_lifecycle_event(
            previous_state="DISCOVERING",
            new_state="DISCOVERING",
            reason=f"Component {interface_id} joined domain",
            capabilities=json.dumps({
                "interface_type": "INTERFACE",
                "service": self.service_name,
                "interface_id": interface_id
            }),
            event_category="NODE_DISCOVERY",
            source_id=interface_id,
            target_id="N/A"  # For node discovery of self, target is same as source
        )

        # Publish legacy monitoring event
        self.publish_monitoring_event(
            "INTERFACE_DISCOVERY",
            metadata={
                "interface_name": self.interface_name,
                "service_name": self.service_name,
                "provider_id": interface_id
            },
            status_data={"status": "available", "state": "ready"}
        )


        # Transition to discovering state
        self.publish_component_lifecycle_event(
            previous_state="JOINING",
            new_state="DISCOVERING",
            reason=f"{interface_id} JOINING -> DISCOVERING",
            capabilities=json.dumps({
                "interface_type": "INTERFACE",
                "service": self.service_name,
                "interface_id": interface_id
            }),
            event_category="STATE_CHANGE",
            source_id=interface_id,
            target_id=interface_id  # For state changes, target is self
        )

        # Transition to ready state
        self.publish_component_lifecycle_event(
            previous_state="DISCOVERING",
            new_state="READY",
            reason=f"{interface_id} DISCOVERING -> READY",
            capabilities=json.dumps({
                "interface_type": "INTERFACE",
                "service": self.service_name,
                "interface_id": interface_id
            }),
            event_category="STATE_CHANGE",
            source_id=interface_id,
            target_id=interface_id  # For state changes, target is self
        )
    
    def publish_monitoring_event(self, 
                               event_type: str,
                               metadata: Optional[Dict[str, Any]] = None,
                               call_data: Optional[Dict[str, Any]] = None,
                               result_data: Optional[Dict[str, Any]] = None,
                               status_data: Optional[Dict[str, Any]] = None,
                               request_info: Optional[Any] = None) -> None:
        """
        Publish a monitoring event.
        
        Args:
            event_type: Type of event (INTERFACE_DISCOVERY, INTERFACE_REQUEST, etc.)
            metadata: Additional metadata about the event
            call_data: Data about the request/call (if applicable)
            result_data: Data about the response/result (if applicable)
            status_data: Data about the interface status (if applicable)
            request_info: Request information containing client ID
        """
        try:
            event = dds.DynamicData(self.monitoring_type)
            
            # Set basic fields
            event["event_id"] = str(uuid.uuid4())
            event["timestamp"] = int(time.time() * 1000)
            event["event_type"] = EVENT_TYPE_MAP[event_type]
            event["entity_type"] = 0  # INTERFACE enum value
            event["entity_id"] = self.interface_name
            
            # Set optional fields
            if metadata:
                event["metadata"] = json.dumps(metadata)
            if call_data:
                event["call_data"] = json.dumps(call_data)
            if result_data:
                event["result_data"] = json.dumps(result_data)
            if status_data:
                event["status_data"] = json.dumps(status_data)
            
            # Write the event
            self.monitoring_writer.write(event)
            logger.debug(f"Published monitoring event: {event_type}")
            
        except Exception as e:
            logger.error(f"Error publishing monitoring event: {str(e)}")
    
    def publish_component_lifecycle_event(self, 
                                       previous_state: str,
                                       new_state: str,
                                       reason: str = "",
                                       capabilities: str = "",
                                       chain_id: str = "",
                                       call_id: str = "",
                                       event_category: str = None,
                                       source_id: str = "",
                                       target_id: str = "",
                                       connection_type: str = None):
        """
        Publish a component lifecycle event for the interface.
        
        Args:
            previous_state: Previous state of the interface (JOINING, DISCOVERING, READY, etc.)
            new_state: New state of the interface
            reason: Reason for the state change
            capabilities: Interface capabilities as JSON string
            chain_id: ID of the chain this event belongs to (if any)
            call_id: Call ID (if any)
            event_category: Category of the event (NODE_DISCOVERY, EDGE_DISCOVERY, STATE_CHANGE)
            source_id: Source ID of the event
            target_id: Target ID of the event
            connection_type: Type of connection for edge discovery events (optional)
        """
        try:
            # Map state strings to enum values
            states = {
                "JOINING": 0,
                "DISCOVERING": 1,
                "READY": 2,
                "BUSY": 3,
                "DEGRADED": 4,
                "OFFLINE": 5
            }
            
            # Map event categories to enum values
            event_categories = {
                "NODE_DISCOVERY": 0,
                "EDGE_DISCOVERY": 1,
                "STATE_CHANGE": 2,
                "AGENT_INIT": 3,
                "AGENT_READY": 4,
                "AGENT_SHUTDOWN": 5,
                "DDS_ENDPOINT": 6
            }
            
            # Get interface ID - this is our component ID
            interface_id = str(self.app.participant.instance_handle)
            
            # Ensure we have a source_id for all events
            if not source_id:
                source_id = interface_id
            
            event = dds.DynamicData(self.component_lifecycle_type)
            event["component_id"] = interface_id
            event["component_type"] = 0  # INTERFACE enum value
            event["previous_state"] = states[previous_state]
            event["new_state"] = states[new_state]
            event["timestamp"] = int(time.time() * 1000)
            event["reason"] = reason
            event["capabilities"] = capabilities
            event["chain_id"] = chain_id
            event["call_id"] = call_id
            
            # Handle event categorization with proper ID requirements
            if event_category:
                event["event_category"] = event_categories[event_category]  # Use direct lookup instead of .get()
                event["source_id"] = source_id
                
                if event_category == "EDGE_DISCOVERY":
                    # For edge events, ensure we have different source and target IDs
                    if not target_id or target_id == source_id:
                        logger.warning("Edge discovery event requires different source and target IDs")
                        return
                    event["target_id"] = target_id
                    event["connection_type"] = connection_type if connection_type else "agent_connection"
                elif event_category == "STATE_CHANGE":
                    # For state changes, both source and target should be the interface ID
                    event["source_id"] = interface_id
                    event["target_id"] = interface_id
                    event["connection_type"] = ""
                else:
                    # For other events, use provided target_id or leave empty
                    event["target_id"] = target_id if target_id else ""
                    event["connection_type"] = ""
            else:
                # Default to state change if no category provided
                event["event_category"] = event_categories["STATE_CHANGE"]
                event["source_id"] = interface_id
                event["target_id"] = interface_id
                event["connection_type"] = ""

            self.component_lifecycle_writer.write(event)
            self.component_lifecycle_writer.flush()
            logger.debug(f"Published component lifecycle event: {previous_state} -> {new_state}")
        except Exception as e:
            logger.error(f"Error publishing component lifecycle event: {e}")
            logger.error(f"Event category was: {event_category}")
    
    def wait_for_agent(self, timeout_seconds: int = 30) -> bool:
        """Wait for agent to be discovered with monitoring"""
        # Generate chain and call IDs for tracking
        chain_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        interface_id = str(self.app.participant.instance_handle)
        
        # Transition to BUSY state
        self.publish_component_lifecycle_event(
            previous_state="READY",
            new_state="BUSY",
            reason=f"{interface_id} READY -> BUSY",
            chain_id=chain_id,
            call_id=call_id,
            event_category="STATE_CHANGE",
            source_id=interface_id
        )
        
        # Publish legacy request event
        self.publish_monitoring_event(
            "INTERFACE_REQUEST",
            metadata={
                "service": self.service_name,
                "chain_id": chain_id,
                "call_id": call_id
            }
        )
        
        try:
            # Call parent method which will handle edge discovery
            result = super().wait_for_agent(timeout_seconds)
            
            if result and hasattr(self, 'agent_info'):
                # Get the agent's ID from agent_info
                provider_id = self.agent_info.get('instance_handle')
                client_id = interface_id
                agent_id = self.agent_info['agent_id']
                
                # Format the edge discovery reason string exactly as expected by the monitor
                reason = f"AGENT Connection: {client_id} -> {provider_id}"
                
                # Publish edge discovery event for the connection
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
                    chain_id=chain_id,
                    call_id=call_id,
                    event_category="EDGE_DISCOVERY",  # This is definitely an edge discovery
                    source_id=client_id,
                    target_id=provider_id,
                    connection_type="agent_connection"
                )
                
                # Publish successful response event
                self.publish_monitoring_event(
                    "INTERFACE_RESPONSE",
                    metadata={
                        "service": self.service_name,
                        "status": "success",
                        "chain_id": chain_id,
                        "call_id": call_id
                    }
                )
                
                # Transition back to READY state
                self.publish_component_lifecycle_event(
                    previous_state="BUSY",
                    new_state="READY",
                    reason=f"{interface_id} BUSY -> READY",
                    chain_id=chain_id,
                    call_id=call_id,
                    event_category="STATE_CHANGE",
                    source_id=interface_id
                )
            else:
                # Publish error event
                self.publish_monitoring_event(
                    "INTERFACE_STATUS",
                    status_data={"error": "Timeout waiting for agent"},
                    metadata={
                        "service": self.service_name,
                        "status": "error",
                        "chain_id": chain_id,
                        "call_id": call_id
                    }
                )
                
                # Transition to DEGRADED state
                self.publish_component_lifecycle_event(
                    previous_state="BUSY",
                    new_state="DEGRADED",
                    reason=f"{interface_id} BUSY -> DEGRADED",
                    chain_id=chain_id,
                    call_id=call_id,
                    event_category="STATE_CHANGE",
                    source_id=interface_id
                )
            
            return result
            
        except Exception as e:
            # Publish error event
            self.publish_monitoring_event(
                "INTERFACE_STATUS",
                status_data={"error": str(e)},
                metadata={
                    "service": self.service_name,
                    "status": "error",
                    "chain_id": chain_id,
                    "call_id": call_id
                }
            )
            
            # Transition to DEGRADED state
            self.publish_component_lifecycle_event(
                previous_state="BUSY",
                new_state="DEGRADED",
                reason=f"{interface_id} BUSY -> DEGRADED",
                chain_id=chain_id,
                call_id=call_id,
                event_category="STATE_CHANGE",
                source_id=interface_id
            )
            raise
    
    def send_request(self, request_data: Dict[str, Any], timeout_seconds: int = 15) -> Optional[Any]:
        """Send request to agent and wait for reply with monitoring"""
        # Generate chain and call IDs for tracking
        chain_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        
        # Transition to BUSY state
        self.publish_component_lifecycle_event(
            previous_state="READY",
            new_state="BUSY",
            reason=f"Sending request to {self.service_name}",
            chain_id=chain_id,
            call_id=call_id
        )
        
        # Create and publish chain event for request start
        chain_event = dds.DynamicData(self.chain_event_type)
        chain_event["chain_id"] = chain_id
        chain_event["call_id"] = call_id
        chain_event["interface_id"] = str(self.app.participant.instance_handle)
        chain_event["primary_agent_id"] = ""  # Will be set when agent is discovered
        chain_event["specialized_agent_ids"] = ""
        chain_event["function_id"] = self.service_name
        chain_event["query_id"] = str(uuid.uuid4())
        chain_event["timestamp"] = int(time.time() * 1000)
        chain_event["event_type"] = "CALL_START"
        chain_event["source_id"] = str(self.app.participant.instance_handle)
        chain_event["target_id"] = "unknown"  # Will be set when agent is discovered
        chain_event["status"] = 0  # Started
        
        self.chain_event_writer.write(chain_event)
        self.chain_event_writer.flush()
        
        # Publish legacy request event
        self.publish_monitoring_event(
            "INTERFACE_REQUEST",
            call_data={"request": request_data},
            metadata={
                "service": self.service_name,
                "chain_id": chain_id,
                "call_id": call_id
            }
        )
        
        try:
            # Call parent method
            result = super().send_request(request_data, timeout_seconds)
            
            if result:
                # Create and publish chain event for request completion
                chain_event = dds.DynamicData(self.chain_event_type)
                chain_event["chain_id"] = chain_id
                chain_event["call_id"] = call_id
                chain_event["interface_id"] = str(self.app.participant.instance_handle)
                chain_event["primary_agent_id"] = ""  # Will be set when agent is discovered
                chain_event["specialized_agent_ids"] = ""
                chain_event["function_id"] = self.service_name
                chain_event["query_id"] = str(uuid.uuid4())
                chain_event["timestamp"] = int(time.time() * 1000)
                chain_event["event_type"] = "CALL_COMPLETE"
                chain_event["source_id"] = "unknown"  # Will be set when agent is discovered
                chain_event["target_id"] = str(self.app.participant.instance_handle)
                chain_event["status"] = 1  # Completed
                
                self.chain_event_writer.write(chain_event)
                self.chain_event_writer.flush()
                
                # Publish successful response event
                self.publish_monitoring_event(
                    "INTERFACE_RESPONSE",
                    result_data={"response": result},
                    metadata={
                        "service": self.service_name,
                        "status": "success",
                        "chain_id": chain_id,
                        "call_id": call_id
                    }
                )
                
                # Transition back to READY state
                self.publish_component_lifecycle_event(
                    previous_state="BUSY",
                    new_state="READY",
                    reason=f"Request completed successfully",
                    chain_id=chain_id,
                    call_id=call_id
                )
            else:
                # Create and publish chain event for request error
                chain_event = dds.DynamicData(self.chain_event_type)
                chain_event["chain_id"] = chain_id
                chain_event["call_id"] = call_id
                chain_event["interface_id"] = str(self.app.participant.instance_handle)
                chain_event["primary_agent_id"] = ""  # Will be set when agent is discovered
                chain_event["specialized_agent_ids"] = ""
                chain_event["function_id"] = self.service_name
                chain_event["query_id"] = str(uuid.uuid4())
                chain_event["timestamp"] = int(time.time() * 1000)
                chain_event["event_type"] = "CALL_ERROR"
                chain_event["source_id"] = "unknown"  # Will be set when agent is discovered
                chain_event["target_id"] = str(self.app.participant.instance_handle)
                chain_event["status"] = 2  # Error
                
                self.chain_event_writer.write(chain_event)
                self.chain_event_writer.flush()
                
                # Publish error event
                self.publish_monitoring_event(
                    "INTERFACE_STATUS",
                    status_data={"error": "No response received"},
                    metadata={
                        "service": self.service_name,
                        "status": "error",
                        "chain_id": chain_id,
                        "call_id": call_id
                    }
                )
                
                # Transition to DEGRADED state
                self.publish_component_lifecycle_event(
                    previous_state="BUSY",
                    new_state="DEGRADED",
                    reason=f"No response received from {self.service_name}",
                    chain_id=chain_id,
                    call_id=call_id
                )
            
            return result
            
        except Exception as e:
            # Create and publish chain event for request error
            chain_event = dds.DynamicData(self.chain_event_type)
            chain_event["chain_id"] = chain_id
            chain_event["call_id"] = call_id
            chain_event["interface_id"] = str(self.app.participant.instance_handle)
            chain_event["primary_agent_id"] = ""  # Will be set when agent is discovered
            chain_event["specialized_agent_ids"] = ""
            chain_event["function_id"] = self.service_name
            chain_event["query_id"] = str(uuid.uuid4())
            chain_event["timestamp"] = int(time.time() * 1000)
            chain_event["event_type"] = "CALL_ERROR"
            chain_event["source_id"] = "unknown"  # Will be set when agent is discovered
            chain_event["target_id"] = str(self.app.participant.instance_handle)
            chain_event["status"] = 2  # Error
            
            self.chain_event_writer.write(chain_event)
            self.chain_event_writer.flush()
            
            # Publish error event
            self.publish_monitoring_event(
                "INTERFACE_STATUS",
                status_data={"error": str(e)},
                metadata={
                    "service": self.service_name,
                    "status": "error",
                    "chain_id": chain_id,
                    "call_id": call_id
                }
            )
            
            # Transition to DEGRADED state
            self.publish_component_lifecycle_event(
                previous_state="BUSY",
                new_state="DEGRADED",
                reason=f"Error sending request to {self.service_name}: {str(e)}",
                chain_id=chain_id,
                call_id=call_id
            )
            raise
    
    async def close(self):
        """Clean up resources"""
        try:
            # First transition to BUSY state for shutdown
            self.publish_component_lifecycle_event(
                previous_state="READY",
                new_state="BUSY",
                reason=f"Interface {self.interface_name} preparing for shutdown"
            )

            # Add a small delay to ensure events are distinguishable
            await asyncio.sleep(0.1)

            # Then transition to OFFLINE
            self.publish_component_lifecycle_event(
                previous_state="BUSY",
                new_state="OFFLINE",
                reason=f"Interface {self.interface_name} shutting down"
            )

            # Publish legacy offline status
            self.publish_monitoring_event(
                "INTERFACE_STATUS",
                status_data={"status": "offline"},
                metadata={"service": self.service_name}
            )
            
            # Close monitoring resources
            if hasattr(self, 'monitoring_writer'):
                self.monitoring_writer.close()
            if hasattr(self, 'monitoring_publisher'):
                self.monitoring_publisher.close()
            if hasattr(self, 'monitoring_topic'):
                self.monitoring_topic.close()
            if hasattr(self, 'component_lifecycle_writer'):
                self.component_lifecycle_writer.close()
            if hasattr(self, 'chain_event_writer'):
                self.chain_event_writer.close()
            if hasattr(self, 'liveliness_writer'):
                self.liveliness_writer.close()
            
            # Close base class resources
            await super().close()
            
        except Exception as e:
            logger.error(f"Error closing monitored interface: {str(e)}") 