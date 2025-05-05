#!/usr/bin/env python3
"""
Monitored agent base class for the GENESIS library.
Provides monitoring capabilities for all agents.
"""

import logging
import time
import uuid
import json
import os
from typing import Any, Dict, Optional, List
import rti.connextdds as dds
import rti.rpc as rpc
from genesis_lib.utils import get_datamodel_path
from .agent import GenesisAgent
import traceback
import asyncio
from datetime import datetime
from genesis_lib.genesis_monitoring import MonitoringSubscriber

# Configure logging
logger = logging.getLogger(__name__)

# Event type mapping
EVENT_TYPE_MAP = {
    "AGENT_DISCOVERY": 0,  # FUNCTION_DISCOVERY enum value
    "AGENT_REQUEST": 1,    # FUNCTION_CALL enum value
    "AGENT_RESPONSE": 2,   # FUNCTION_RESULT enum value
    "AGENT_STATUS": 3      # FUNCTION_STATUS enum value
}

# Agent type mapping
AGENT_TYPE_MAP = {
    "AGENT": 1,            # PRIMARY_AGENT
    "SPECIALIZED_AGENT": 2, # SPECIALIZED_AGENT
    "INTERFACE": 0         # INTERFACE
}

# Event category mapping
EVENT_CATEGORY_MAP = {
    "NODE_DISCOVERY": 0,
    "EDGE_DISCOVERY": 1,
    "STATE_CHANGE": 2,
    "AGENT_INIT": 3,
    "AGENT_READY": 4
}

class MonitoredAgent(GenesisAgent):
    """
    Base class for agents with monitoring capabilities.
    Extends GenesisAgent to add standardized monitoring.
    """
    
    def __init__(self, agent_name: str, service_name: str, agent_type: str = "AGENT", agent_id: str = None,
                 description: str = None, domain_id: int = 0):
        """
        Initialize the monitored agent.
        
        Args:
            agent_name: Name of the agent
            service_name: Name of the service this agent provides
            agent_type: Type of agent (AGENT, SPECIALIZED_AGENT)
            agent_id: Optional UUID for the agent (if None, will generate one)
            description: Optional description of the agent
            domain_id: Optional DDS domain ID
        """
        logger.info(f"MonitoredAgent {agent_name} STARTING initializing with agent_id {agent_id}")
        # Initialize base class with only the parameters it accepts
        super().__init__(
            agent_name=agent_name,
            service_name=service_name,
            agent_id=agent_id
        )
        logger.info(f"MonitoredAgent {agent_name} initialized with base class")
        # Store additional parameters as instance variables
        self.agent_type = agent_type
        self.description = description or f"A {agent_type} providing {service_name} service"
        self.domain_id = domain_id
        self.monitor = None
        self.subscription = None
        
        # Initialize agent capabilities
        self.agent_capabilities = {
            "agent_type": agent_type,
            "service": service_name,
            "functions": [],  # Will be populated during function discovery
            "supported_tasks": []  # To be populated by subclasses
        }
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.request_type = self.type_provider.type("genesis_lib", f"{service_name}Request")
        self.reply_type = self.type_provider.type("genesis_lib", f"{service_name}Reply")
        
        # Set up monitoring
        self._setup_monitoring()
        
        # Create subscription match listener
        self._setup_subscription_listener()

        # Publish agent discovery event
        self.publish_component_lifecycle_event(
            category="NODE_DISCOVERY",
            message=f"Agent {agent_name} discovered",
            previous_state="OFFLINE",
            new_state="DISCOVERING",
            source_id=self.app.agent_id,
            target_id=self.app.agent_id,
            capabilities=json.dumps({
                "agent_type": agent_type,
                "service": service_name,
                "description": self.description,
                "agent_id": self.app.agent_id
            })
        )

        # Publish agent ready event
        self.publish_component_lifecycle_event(
            category="AGENT_READY",
            message=f"{agent_name} ready for requests",
            previous_state="DISCOVERING",
            new_state="READY",
            source_id=self.app.agent_id,
            target_id=self.app.agent_id,
            capabilities=json.dumps({
                "agent_type": agent_type,
                "service": service_name,
                "description": self.description,
                "agent_id": self.app.agent_id
            })
        )
        
        logger.info(f"Monitored agent {agent_name} initialized with type {agent_type}, agent_id={self.app.agent_id}, dds_guid={self.app.dds_guid}")
    
    def _setup_monitoring(self) -> None:
        """
        Set up monitoring resources and initialize state.
        """
        try:
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

            # Create writers for each monitoring type using the same publisher
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
            
            # Initialize state tracking
            self.current_state = "OFFLINE"
            self.last_state_change = datetime.now()
            self.state_history = []
            self.event_correlation = {}
            
            # Publish initial state
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message="Initializing monitoring",
                previous_state="OFFLINE",
                new_state="INITIALIZING",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            self.current_state = "INITIALIZING"
            
            # Set up event correlation tracking
            self.event_correlation = {
                "monitoring_events": {},
                "lifecycle_events": {},
                "chain_events": {}
            }
            
            # Transition to READY state
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message="Monitoring initialized successfully",
                previous_state="INITIALIZING",
                new_state="READY",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            self.current_state = "READY"
            
        except Exception as e:
            logger.error(f"Failed to initialize monitoring: {e}")
            self.current_state = "DEGRADED"
            raise
    
    def _setup_subscription_listener(self):
        """Set up a listener to track subscription matches"""
        class SubscriptionMatchListener(dds.DynamicData.NoOpDataReaderListener):
            def __init__(self, logger):
                super().__init__()
                self.logger = logger
                
            def on_subscription_matched(self, reader, status):
                # Only log matches for ComponentLifecycleEvent topic
                if reader.topic_description.name != "ComponentLifecycleEvent":
                    return
                    
                self.logger.info(
                    "ComponentLifecycleEvent subscription matched",
                    extra={
                        "topic": reader.topic_description.name,
                        "remote_guid": str(status.last_publication_handle),
                        "current_count": status.current_count
                    }
                )

        # Create reader with the subscription match listener
        reader_qos = dds.QosProvider.default.datareader_qos
        reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        
        # Add listener to component lifecycle reader
        self.component_lifecycle_reader = dds.DynamicData.DataReader(
            subscriber=self.app.subscriber,
            topic=self.component_lifecycle_topic,
            qos=reader_qos,
            listener=SubscriptionMatchListener(logger),
            mask=dds.StatusMask.SUBSCRIPTION_MATCHED
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
            event_type: Type of event (AGENT_DISCOVERY, AGENT_REQUEST, etc.)
            metadata: Additional metadata about the event
            call_data: Data about the request/call (if applicable)
            result_data: Data about the response/result (if applicable)
            status_data: Data about the agent status (if applicable)
            request_info: Request information containing client ID
        """
        try:
            event = dds.DynamicData(self.monitoring_type)
            
            # Set basic fields
            event["event_id"] = str(uuid.uuid4())
            event["timestamp"] = int(time.time() * 1000)
            event["event_type"] = EVENT_TYPE_MAP[event_type]
            event["entity_type"] = AGENT_TYPE_MAP.get(self.agent_type, 1)  # Default to PRIMARY_AGENT if type not found
            event["entity_id"] = self.agent_name
            
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
            logger.error(traceback.format_exc())
    
    def publish_component_lifecycle_event(self, 
                                       category: str,
                                       message: str = None,
                                       previous_state: str = None,
                                       new_state: str = None,
                                       reason: str = None,
                                       capabilities: str = None,
                                       component_id: str = None,
                                       source_id: str = None,
                                       target_id: str = None,
                                       connection_type: str = None):
        """
        Publish a component lifecycle event for the agent.
        
        Args:
            category: Event category (e.g., EDGE_DISCOVERY, EDGE_READY)
            message: Optional message to include with the event
            previous_state: Previous state of the component
            new_state: New state of the component
            reason: Reason for the state change
            capabilities: JSON string of component capabilities
            component_id: ID of the component
            source_id: Source ID for edge events
            target_id: Target ID for edge events
            connection_type: Type of connection for edge events
        """
        try:
            if not hasattr(self, 'component_lifecycle_type') or not self.component_lifecycle_type:
                logger.debug(f"Component lifecycle monitoring not initialized, skipping event: {category}")
                return
            
            if not hasattr(self, 'component_lifecycle_writer') or not self.component_lifecycle_writer:
                logger.debug(f"Component lifecycle writer not initialized, skipping event: {category}")
                return

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

            # Create event
            event = dds.DynamicData(self.component_lifecycle_type)
            
            # Set component ID (use provided ID or agent name)
            event["component_id"] = component_id if component_id else self.agent_name
            
            # Set component type (AGENT for agent)
            event["component_type"] = 2
            
            # Set states based on category or provided states
            if previous_state and new_state:
                event["previous_state"] = states.get(previous_state, states["DISCOVERING"])
                event["new_state"] = states.get(new_state, states["DISCOVERING"])
            else:
                if category == "NODE_DISCOVERY":
                    event["previous_state"] = states["DISCOVERING"]
                    event["new_state"] = states["DISCOVERING"]
                elif category == "AGENT_INIT":
                    event["previous_state"] = states["OFFLINE"]
                    event["new_state"] = states["JOINING"]
                elif category == "AGENT_READY":
                    event["previous_state"] = states["DISCOVERING"]
                    event["new_state"] = states["READY"]
                elif category == "BUSY":
                    event["previous_state"] = states["READY"]
                    event["new_state"] = states["BUSY"]
                elif category == "READY":
                    event["previous_state"] = states["BUSY"]
                    event["new_state"] = states["READY"]
                elif category == "DEGRADED":
                    event["previous_state"] = states["BUSY"]
                    event["new_state"] = states["DEGRADED"]
                else:
                    event["previous_state"] = states["DISCOVERING"]
                    event["new_state"] = states["DISCOVERING"]
            
            # Set other fields
            event["timestamp"] = int(time.time() * 1000)
            event["reason"] = reason if reason else (message if message else "")
            event["capabilities"] = capabilities if capabilities else json.dumps(self.agent_capabilities)
            
            # Set event category
            if category in event_categories:
                event["event_category"] = event_categories[category]
            else:
                event["event_category"] = event_categories["NODE_DISCOVERY"]
            
            # Set source and target IDs, defaulting to self.app.agent_id
            event["source_id"] = source_id if source_id else self.app.agent_id
            if category == "EDGE_DISCOVERY":
                # For edge discovery, target is the function being discovered
                event["target_id"] = target_id if target_id else self.app.agent_id
                event["connection_type"] = connection_type if connection_type else "function_connection"
            else:
                # For other events, source and target are the same (self.app.agent_id)
                event["target_id"] = target_id if target_id else self.app.agent_id
                event["connection_type"] = connection_type if connection_type else ""

            self.component_lifecycle_writer.write(event)
            self.component_lifecycle_writer.flush()
        except Exception as e:
            logger.error(f"Error publishing component lifecycle event: {e}")
            logger.error(f"Event category was: {category}")
    
    async def process_request(self, request: Any) -> Dict[str, Any]:
        """
        Process a request with monitoring.
        
        This implementation wraps the concrete process_request with monitoring events.
        Concrete implementations should override _process_request instead.
        
        Args:
            request: The request to process
            
        Returns:
            Dictionary containing the response data
        """
        # Generate chain and call IDs for tracking
        chain_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())

        try:
            # Ensure we're in READY state before processing
            if self.current_state != "READY":
                self.publish_component_lifecycle_event(
                    category="STATE_CHANGE",
                    message=f"Transitioning to READY state before processing request",
                    previous_state=self.current_state,
                    new_state="READY",
                    source_id=self.app.agent_id,
                    target_id=self.app.agent_id
                )
                self.current_state = "READY"

            # Transition to BUSY state
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message=f"Processing request: {str(request)}",
                previous_state="READY",
                new_state="BUSY",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            self.current_state = "BUSY"

            # Publish legacy request received event
            self.publish_monitoring_event(
                "AGENT_REQUEST",
                call_data={"request": str(request)},
                metadata={
                    "service": self.service_name,
                    "chain_id": chain_id,
                    "call_id": call_id
                }
            )
            
            # Process request using concrete implementation
            result = await self._process_request(request)
            
            # Publish successful response event
            self.publish_monitoring_event(
                "AGENT_RESPONSE",
                result_data={"response": str(result)},
                metadata={
                    "service": self.service_name,
                    "status": "success",
                    "chain_id": chain_id,
                    "call_id": call_id
                }
            )

            # Transition back to READY state
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message=f"Request processed successfully: {str(result)}",
                previous_state="BUSY",
                new_state="READY",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            self.current_state = "READY"
            
            return result
            
        except Exception as e:
            # Publish error event
            self.publish_monitoring_event(
                "AGENT_STATUS",
                status_data={"error": str(e)},
                metadata={
                    "service": self.service_name,
                    "status": "error",
                    "chain_id": chain_id,
                    "call_id": call_id
                }
            )

            # Transition to DEGRADED state on error
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message=f"Error processing request: {str(e)}",
                previous_state=self.current_state,
                new_state="DEGRADED",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            self.current_state = "DEGRADED"
            
            # Attempt recovery by transitioning back to READY
            try:
                self.publish_component_lifecycle_event(
                    category="STATE_CHANGE",
                    message="Attempting recovery to READY state",
                    previous_state="DEGRADED",
                    new_state="READY",
                    source_id=self.app.agent_id,
                    target_id=self.app.agent_id
                )
                self.current_state = "READY"
            except Exception as recovery_error:
                logger.error(f"Failed to recover from DEGRADED state: {recovery_error}")
            
            raise
    
    def _process_request(self, request: Any) -> Dict[str, Any]:
        """
        Process the request and return reply data.
        
        This method should be overridden by concrete implementations.
        
        Args:
            request: The request to process
            
        Returns:
            Dictionary containing the response data
        """
        raise NotImplementedError("Concrete agents must implement _process_request")
    
    async def close(self) -> None:
        """
        Close monitoring resources and transition to OFFLINE state.
        """
        try:
            # Transition to OFFLINE state
            self.publish_component_lifecycle_event(
                category="STATE_CHANGE",
                message="Shutting down monitoring",
                previous_state=self.current_state,
                new_state="OFFLINE",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            
            # Detach listener first to potentially resolve waitset issues
            if hasattr(self, 'component_lifecycle_reader'):
                self.component_lifecycle_reader.set_listener(None, dds.StatusMask.NONE)
                self.component_lifecycle_reader.close() # Also close the reader itself

            # Clean up monitoring resources
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
            if hasattr(self, 'component_lifecycle_topic'):
                self.component_lifecycle_topic.close()
            if hasattr(self, 'chain_event_topic'):
                self.chain_event_topic.close()
            if hasattr(self, 'liveliness_topic'):
                self.liveliness_topic.close()
            
            # Clear state tracking
            self.current_state = "OFFLINE"
            self.last_state_change = datetime.now()
            self.state_history = []
            self.event_correlation = {}
            
            # Call parent class cleanup
            if hasattr(self, 'app'):
                await self.app.close()
            
        except Exception as e:
            logger.error(f"Error during monitoring shutdown: {e}")
            self.current_state = "DEGRADED"
            raise

    def wait_for_agent(self) -> bool:
        """
        Wait for an agent to become available.
        Now includes edge discovery events for multiple connections.
        """
        try:
            logger.info("Starting wait_for_agent")
            # Wait for agent using base class implementation
            result = super().wait_for_agent()
            logger.info(f"Base wait_for_agent returned: {result}")

            if result:
                # Get all discovered agents' information
                agent_infos = self.app.get_all_agent_info()
                logger.info(f"Got agent infos: {agent_infos}")
                
                for agent_info in agent_infos:
                    if agent_info:
                        # Format the edge discovery reason string exactly as expected by the monitor
                        # This format is critical for the monitor to recognize it as an edge discovery event
                        provider_id = str(agent_info.get('instance_handle', ''))
                        client_id = str(self.app.participant.instance_handle)
                        function_id = str(uuid.uuid4())
                        
                        # Format exactly as monitor expects for edge discovery
                        reason = f"provider={provider_id} client={client_id} function={function_id} name={self.service_name}"
                        logger.info(f"Publishing edge discovery event with reason: {reason}")

                        # Publish edge discovery event while in DISCOVERING state
                        self.publish_component_lifecycle_event(
                            category="EDGE_DISCOVERY",
                            message=reason,
                            capabilities=json.dumps({
                                "agent_type": self.agent_type,
                                "service": self.service_name,
                                "edge_type": "agent_function",
                                "provider_id": provider_id,
                                "client_id": client_id,
                                "function_id": function_id
                            }),
                            source_id=self.app.agent_id,
                            target_id=self.app.agent_id
                        )
                        logger.info("Published edge discovery event")

                        # Add a small delay to ensure events are distinguishable
                        time.sleep(0.1)

            return result

        except Exception as e:
            logger.error(f"Error in wait_for_agent: {str(e)}")
            # Transition to degraded state on error
            self.publish_component_lifecycle_event(
                category="DEGRADED",
                message=f"Error discovering functions: {str(e)}",
                source_id=self.app.agent_id,
                target_id=self.app.agent_id
            )
            return False


    
    def _get_requester_guid(self, function_client) -> str:
        """
        Extract the DDS GUID of the requester from a function client.
        
        Args:
            function_client: An instance of a function client
            
        Returns:
            The DDS GUID of the requester, or None if not available
        """
        requester_guid = None
        
        try:
            # Try different paths to get the requester GUID
            if hasattr(function_client, 'requester') and hasattr(function_client.requester, 'request_datawriter'):
                requester_guid = str(function_client.requester.request_datawriter.instance_handle)
                logger.info(f"===== TRACING: Got requester GUID from request_datawriter: {requester_guid} =====")
            elif hasattr(function_client, 'requester') and hasattr(function_client.requester, 'participant'):
                requester_guid = str(function_client.requester.participant.instance_handle)
                logger.info(f"===== TRACING: Got requester GUID from participant: {requester_guid} =====")
            elif hasattr(function_client, 'participant'):
                requester_guid = str(function_client.participant.instance_handle)
                logger.info(f"===== TRACING: Got requester GUID from client participant: {requester_guid} =====")
        except Exception as e:
            logger.error(f"===== TRACING: Error getting requester GUID: {e} =====")
            logger.error(traceback.format_exc())
            
        return requester_guid
    
    def store_function_requester_guid(self, guid: str):
        """
        Store the function requester GUID and create edges to known function providers.
        
        Args:
            guid: The DDS GUID of the function requester
        """
        logger.info(f"===== TRACING: Storing function requester GUID: {guid} =====")
        self.function_requester_guid = guid
        
        # Create edges to all known function providers
        if hasattr(self, 'function_provider_guids'):
            for provider_guid in self.function_provider_guids:
                try:
                    # Create a unique edge key
                    edge_key = f"direct_requester_to_provider_{guid}_{provider_guid}"
                    
                    # Publish direct edge discovery event
                    self.publish_component_lifecycle_event(
                        category="EDGE_DISCOVERY",
                        message=f"Direct connection: {guid} -> {provider_guid}",
                        capabilities=json.dumps({
                            "edge_type": "direct_connection",
                            "requester_guid": guid,
                            "provider_guid": provider_guid,
                            "agent_id": self.app.agent_id,
                            "agent_name": self.agent_name,
                            "service_name": self.service_name
                        }),
                        source_id=guid,
                        target_id=provider_guid,
                        connection_type="CONNECTS_TO"
                    )
                    
                    logger.info(f"===== TRACING: Published direct requester-to-provider edge: {guid} -> {provider_guid} =====")
                except Exception as e:
                    logger.error(f"===== TRACING: Error publishing direct requester-to-provider edge: {e} =====")
                    logger.error(traceback.format_exc())
    
    def store_function_provider_guid(self, guid: str):
        """
        Store a function provider GUID and create an edge if the function requester is known.
        
        Args:
            guid: The DDS GUID of the function provider
        """
        logger.info(f"===== TRACING: Storing function provider GUID: {guid} =====")
        
        # Initialize the set if it doesn't exist
        if not hasattr(self, 'function_provider_guids'):
            self.function_provider_guids = set()
            
        # Add the provider GUID to the set
        self.function_provider_guids.add(guid)
        
        # Create an edge if the function requester is known
        if hasattr(self, 'function_requester_guid') and self.function_requester_guid:
            try:
                # Create a unique edge key
                edge_key = f"direct_requester_to_provider_{self.function_requester_guid}_{guid}"
                
                # Publish direct edge discovery event
                self.publish_component_lifecycle_event(
                    category="EDGE_DISCOVERY",
                    message=f"Direct connection: {self.function_requester_guid} -> {guid}",
                    capabilities=json.dumps({
                        "edge_type": "direct_connection",
                        "requester_guid": self.function_requester_guid,
                        "provider_guid": guid,
                        "agent_id": self.app.agent_id,
                        "agent_name": self.agent_name,
                        "service_name": self.service_name
                    }),
                    source_id=self.function_requester_guid,
                    target_id=guid,
                    connection_type="CONNECTS_TO"
                )
                
                logger.info(f"===== TRACING: Published direct requester-to-provider edge: {self.function_requester_guid} -> {guid} =====")
            except Exception as e:
                logger.error(f"===== TRACING: Error publishing direct requester-to-provider edge: {e} =====")
                logger.error(traceback.format_exc())
    
    def publish_discovered_functions(self, functions: List[Dict[str, Any]]) -> None:
        """
        Publish discovered functions as monitoring events.
        
        Args:
            functions: List of discovered functions
        """
        logger.info(f"===== TRACING: Publishing {len(functions)} discovered functions as monitoring events =====")
        
        # Get the function requester DDS GUID if available
        function_requester_guid = None
        
        # First try to get it from the stored function client
        if hasattr(self, 'function_client'):
            function_requester_guid = self._get_requester_guid(self.function_client)
            
            # Store the function requester GUID for later use
            if function_requester_guid:
                self.function_requester_guid = function_requester_guid
                logger.info(f"===== TRACING: Stored function requester GUID: {function_requester_guid} =====")
            
        # If we still don't have it, try other methods
        if not function_requester_guid and hasattr(self, 'app') and hasattr(self.app, 'function_registry'):
            try:
                function_requester_guid = str(self.app.function_registry.participant.instance_handle)
                logger.info(f"===== TRACING: Function requester GUID from registry: {function_requester_guid} =====")
                
                # Store the function requester GUID for later use
                self.function_requester_guid = function_requester_guid
                logger.info(f"===== TRACING: Stored function requester GUID: {function_requester_guid} =====")
            except Exception as e:
                logger.error(f"===== TRACING: Error getting function requester GUID from registry: {e} =====")
        
        # Collect provider GUIDs from discovered functions
        provider_guids = set()
        function_provider_guid = None
        
        for func in functions:
            if 'provider_id' in func and func['provider_id']:
                provider_guid = func['provider_id']
                provider_guids.add(provider_guid)
                logger.info(f"===== TRACING: Found provider GUID: {provider_guid} =====")
                
                # Store the provider GUID for later use
                self.store_function_provider_guid(provider_guid)
                
                # Store the first provider GUID as the main function provider GUID
                if function_provider_guid is None:
                    function_provider_guid = provider_guid
                    logger.info(f"===== TRACING: Using {function_provider_guid} as the main function provider GUID =====")
        
        # Publish a monitoring event for each discovered function
        for func in functions:
            function_id = func.get('function_id', str(uuid.uuid4()))
            function_name = func.get('name', 'unknown')
            provider_id = func.get('provider_id', '')
            
            # Publish as a component lifecycle event
            self.publish_component_lifecycle_event(
                category="NODE_DISCOVERY",
                message=f"Function discovered: {function_name} ({function_id})",
                capabilities=json.dumps({
                    "function_id": function_id,
                    "function_name": function_name,
                    "function_description": func.get('description', ''),
                    "function_schema": func.get('schema', {}),
                    "provider_id": provider_id,
                    "provider_name": func.get('provider_name', '')
                }),
                source_id=self.app.agent_id,
                target_id=function_id,
                connection_type="FUNCTION"
            )
            
            # Also publish an edge discovery event connecting the agent to the function
            self.publish_component_lifecycle_event(
                category="EDGE_DISCOVERY",
                message=f"Agent {self.agent_name} can call function {function_name}",
                capabilities=json.dumps({
                    "edge_type": "agent_function",
                    "function_id": function_id,
                    "function_name": function_name
                }),
                source_id=self.app.agent_id,
                target_id=function_id,
                connection_type="CALLS"
            )
            
            # Also publish as a legacy monitoring event
            self.publish_monitoring_event(
                "AGENT_DISCOVERY",
                metadata={
                    "function_id": function_id,
                    "function_name": function_name,
                    "provider_id": provider_id,
                    "provider_name": func.get('provider_name', '')
                },
                status_data={
                    "status": "available",
                    "state": "discovered",
                    "description": func.get('description', ''),
                    "schema": json.dumps(func.get('schema', {}))
                }
            )
            
            logger.info(f"===== TRACING: Published function discovery event for {function_name} ({function_id}) =====")
        
        # Publish edge discovery events connecting the function requester to each provider
        if function_requester_guid:
            for provider_guid in provider_guids:
                if provider_guid:
                    try:
                        # Create a unique edge key
                        edge_key = f"requester_to_provider_{function_requester_guid}_{provider_guid}"
                        
                        # Publish edge discovery event
                        self.publish_component_lifecycle_event(
                            category="EDGE_DISCOVERY",
                            message=f"Function requester connects to provider: {function_requester_guid} -> {provider_guid}",
                            capabilities=json.dumps({
                                "edge_type": "requester_provider",
                                "requester_guid": function_requester_guid,
                                "provider_guid": provider_guid,
                                "agent_id": self.app.agent_id,
                                "agent_name": self.agent_name
                            }),
                            source_id=function_requester_guid,
                            target_id=provider_guid,
                            connection_type="DISCOVERS"
                        )
                        
                        logger.info(f"===== TRACING: Published requester-to-provider edge: {function_requester_guid} -> {provider_guid} =====")
                    except Exception as e:
                        logger.error(f"===== TRACING: Error publishing requester-to-provider edge: {e} =====")
                        logger.error(traceback.format_exc())
        
        # If we have both the function requester GUID and the main function provider GUID,
        # create a direct edge between them
        if function_provider_guid:
            try:
                # Create a unique edge key for the direct connection
                direct_edge_key = f"direct_requester_to_provider_{function_requester_guid}_{function_provider_guid}"
                
                # Publish direct edge discovery event
                self.publish_component_lifecycle_event(
                    category="EDGE_DISCOVERY",
                    message=f"Direct connection: {function_requester_guid} -> {function_provider_guid}",
                    capabilities=json.dumps({
                        "edge_type": "direct_connection",
                        "requester_guid": function_requester_guid,
                        "provider_guid": function_provider_guid,
                        "agent_id": self.app.agent_id,
                        "agent_name": self.agent_name,
                        "service_name": self.service_name
                    }),
                    source_id=function_requester_guid,
                    target_id=function_provider_guid,
                    connection_type="CONNECTS_TO"
                )
                
                logger.info(f"===== TRACING: Published direct requester-to-provider edge: {function_requester_guid} -> {function_provider_guid} =====")
            except Exception as e:
                logger.error(f"===== TRACING: Error publishing direct requester-to-provider edge: {e} =====")
                logger.error(traceback.format_exc())
        else:
            logger.warning("===== TRACING: Could not publish requester-to-provider edge: function_requester_guid not available =====")
        
        # Log a summary of all discovered functions
        function_names = [f.get('name', 'unknown') for f in functions]
        logger.info(f"===== TRACING: MonitoredAgent has discovered these functions: {function_names} =====")
        
        # Transition to READY state after discovering functions
        self.publish_component_lifecycle_event(
            category="READY",
            message=f"Agent {self.agent_name} discovered {len(functions)} functions and is ready",
            capabilities=json.dumps({
                "agent_type": self.agent_type,
                "service": self.service_name,
                "discovered_functions": len(functions),
                "function_names": function_names
            }),
            source_id=self.app.agent_id,
            target_id=self.app.agent_id
        )

    def create_requester_provider_edge(self, requester_guid: str, provider_guid: str):
        """
        Explicitly create an edge between a function requester and provider.
        
        Args:
            requester_guid: The DDS GUID of the function requester
            provider_guid: The DDS GUID of the function provider
        """
        logger.info(f"===== TRACING: Creating explicit requester-to-provider edge: {requester_guid} -> {provider_guid} =====")
        
        try:
            # Create a unique edge key
            edge_key = f"explicit_requester_to_provider_{requester_guid}_{provider_guid}"
            
            # Publish direct edge discovery event
            self.publish_component_lifecycle_event(
                category="EDGE_DISCOVERY",
                message=f"Explicit connection: {requester_guid} -> {provider_guid}",
                capabilities=json.dumps({
                    "edge_type": "explicit_connection",
                    "requester_guid": requester_guid,
                    "provider_guid": provider_guid,
                    "agent_id": self.app.agent_id,
                    "agent_name": self.agent_name,
                    "service_name": self.service_name
                }),
                source_id=requester_guid,
                target_id=provider_guid,
                connection_type="CONNECTS_TO"
            )
            
            logger.info(f"===== TRACING: Published explicit requester-to-provider edge: {requester_guid} -> {provider_guid} =====")
            return True
        except Exception as e:
            logger.error(f"===== TRACING: Error publishing explicit requester-to-provider edge: {e} =====")
            logger.error(traceback.format_exc())
            return False

    def set_agent_capabilities(self, supported_tasks: list[str] = None, additional_capabilities: dict = None):
        """
        Set or update agent capabilities in a user-friendly way.
        
        Args:
            supported_tasks: List of tasks this agent can perform
            additional_capabilities: Dictionary of additional capability metadata
        """
        if supported_tasks:
            self.agent_capabilities["supported_tasks"] = supported_tasks
            
        if additional_capabilities:
            self.agent_capabilities.update(additional_capabilities)
            
        # Publish updated capabilities
        self.publish_component_lifecycle_event(
            category="STATE_CHANGE",
            message="Agent capabilities updated",
            capabilities=json.dumps(self.agent_capabilities),
            source_id=self.app.agent_id,
            target_id=self.app.agent_id
        ) 