#!/usr/bin/env python3
"""
Genesis Enhanced Service Base

This module provides the core base class for all services in the Genesis framework,
implementing automatic function discovery, registration, and monitoring capabilities.
It serves as the foundation for exposing functions to large language models and agents
within the Genesis network.

Key responsibilities include:
- Automatic function registration and discovery for LLM tool use
- Comprehensive monitoring and event tracking
- Function capability advertisement and lifecycle management
- Enhanced error handling and resource management
- Integration with the Genesis monitoring system
- Support for function decorators and automatic schema generation

The EnhancedServiceBase class enables services to:
1. Automatically expose their functions to LLMs and agents
2. Track function calls, results, and errors
3. Monitor service and function lifecycle events
4. Manage function capabilities and discovery
5. Handle complex RPC interactions with proper monitoring

This is the primary integration point for services that want to participate
in the Genesis network's function calling ecosystem.

Copyright (c) 2025, RTI & Jason Upchurch
"""

import logging
import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from genesis_lib.rpc_service import GenesisRPCService
from genesis_lib.function_discovery import FunctionRegistry, FunctionCapabilityListener
import rti.connextdds as dds
from genesis_lib.logging_config import configure_genesis_logging
from genesis_lib.datamodel import FunctionRequest, FunctionReply
import re
import uuid
import time
import os
from genesis_lib.utils import get_datamodel_path

# Monitoring event type constants
EVENT_TYPE_MAP = {
    "FUNCTION_DISCOVERY": 0,  # Legacy discovery event
    "FUNCTION_CALL": 1,
    "FUNCTION_RESULT": 2,
    "FUNCTION_STATUS": 3,
    "FUNCTION_DISCOVERY_V2": 4  # New discovery event format
}

ENTITY_TYPE_MAP = {
    "FUNCTION": 0,
    "SERVICE": 1,
    "NODE": 2
}


# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("enhanced_service_base")

class EnhancedFunctionCapabilityListener(FunctionCapabilityListener):
    def __init__(self, registry, service_base):
        super().__init__(registry)
        self.service_base = service_base

    def on_subscription_matched(self, reader, info):
        """Handle subscription matches"""
        # First check if this is a FunctionCapability topic match
        if reader.topic_name != "FunctionCapability":
            print(f"Ignoring subscription match for topic: {reader.topic_name}")
            return
            
        # Now we know this is a FunctionCapability topic match
        remote_guid = str(info.last_publication_handle)
        self_guid = str(self.registry.capability_writer.instance_handle) or "0"
        
        # Format the reason string for edge discovery
        edge_reason = f"provider={self_guid} client={remote_guid} function={remote_guid}"
        edge_capabilities = {
            "edge_type": "function_connection",
            "source_id": self_guid,
            "target_id": remote_guid,
            "topic": reader.topic_name
        }
        
        # Publish edge discovery event
        self.service_base.publish_component_lifecycle_event(
            previous_state="DISCOVERING",
            new_state="DISCOVERING",
            reason=edge_reason,
            capabilities=json.dumps(edge_capabilities),
            component_id=self_guid,
            event_category="EDGE_DISCOVERY",
            source_id=self_guid,
            target_id=remote_guid,
            connection_type="function_connection"
        )
        
       # print(f"FunctionCapability subscription matched with remote GUID: {remote_guid}")
       # print(f"FunctionCapability subscription matched with self GUID:   {self_guid}")

class EnhancedServiceBase(GenesisRPCService):
    """
    Enhanced base class for GENESIS RPC services.
    
    This class abstracts common functionality for:
    1. Function registration and discovery
    2. Monitoring event publication
    3. Error handling
    4. Resource management
    
    Services that extend this class need to:
    1. Call super().__init__(service_name="YourServiceName")
    2. Register their functions using register_enhanced_function()
    3. Implement their function methods with the standard pattern
    """
    
    def __init__(self, service_name: str, capabilities: List[str], participant=None, domain_id=0, registry: FunctionRegistry = None):
        """
        Initialize the enhanced service base.
        
        Args:
            service_name: Unique name for the service
            capabilities: List of service capabilities for discovery
            registry: Optional FunctionRegistry instance. If None, creates a new one.
        """
        # Initialize the base RPC service
        super().__init__(service_name=service_name)
        
        # Store service name as instance variable
        self.service_name = service_name
        
        # Create DDS participant if not provided
        if participant is None:
            participant = dds.DomainParticipant(domain_id)
        
        # Store participant reference
        self.participant = participant
        
        # Create subscriber
        self.subscriber = dds.Subscriber(participant)
        
        # Create publisher
        self.publisher = dds.Publisher(participant)

        # Use Python IDL types from datamodel.py
        self.request_type = FunctionRequest
        self.reply_type = FunctionReply
        
        # Get types from XML for monitoring
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        
        # Set up monitoring
        self.monitoring_type = self.type_provider.type("genesis_lib", "MonitoringEvent")
        self.monitoring_topic = dds.DynamicData.Topic(
            participant,
            "MonitoringEvent",
            self.monitoring_type
        )
        
        # Create monitoring publisher with QoS
        publisher_qos = dds.QosProvider.default.publisher_qos
        publisher_qos.partition.name = [""]  # Default partition
        self.monitoring_publisher = dds.Publisher(
            participant=participant,
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
        
        # Set up enhanced monitoring (V2) - MOVED UP before registry initialization
        # Create topics for new monitoring types
        self.component_lifecycle_type = self.type_provider.type("genesis_lib", "ComponentLifecycleEvent")
        self.chain_event_type = self.type_provider.type("genesis_lib", "ChainEvent")
        self.liveliness_type = self.type_provider.type("genesis_lib", "LivelinessUpdate")

        # Create topics
        self.component_lifecycle_topic = dds.DynamicData.Topic(
            participant,
            "ComponentLifecycleEvent",
            self.component_lifecycle_type
        )
        self.chain_event_topic = dds.DynamicData.Topic(
            participant,
            "ChainEvent",
            self.chain_event_type
        )
        self.liveliness_topic = dds.DynamicData.Topic(
            participant,
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
        
        # Now we can auto-register decorated functions
        self._auto_register_decorated_functions()
        
        # Get DDS instance handle for consistent identification - will be set after registry is initialized
        self.app_guid = None  # Will be set after capability writer is created
        
        # Initialize the function registry and store reference to self
        self.registry = registry if registry is not None else FunctionRegistry(participant=self.participant, domain_id=domain_id)
        self.registry.service_base = self  # Set this instance as the service base

        # Create and set our enhanced listener
        self.capability_listener = EnhancedFunctionCapabilityListener(self.registry, self)
        self.registry.capability_reader.listener = self.capability_listener
        
        # Now set app_guid using the capability writer's instance handle
        self.app_guid = str(self.registry.capability_writer.instance_handle)
        
        # Store service capabilities
        self.service_capabilities = capabilities
        
        # Flag to track if functions have been advertised
        self._functions_advertised = False

        # Track call IDs for correlation between calls and results
        self._call_ids = {}

        # Initialize logger
        self.logger = logging.getLogger("enhanced_service_base")
    
    # ---------------------------------------------------------------------- #
    # Decorator auto‑scan                                                    #
    # ---------------------------------------------------------------------- #
    def _auto_register_decorated_functions(self):
        """
        Detect methods that carry __genesis_meta__ (set by @genesis_function)
        and register them via existing register_enhanced_function().
        """
        for attr in dir(self):
            fn = getattr(self, attr)
            meta = getattr(fn, "__genesis_meta__", None)
            if not meta:
                continue
            if fn.__name__ in self.functions:          # Already registered?
                continue
            self.register_enhanced_function(
                fn,
                meta["description"],
                meta["parameters"],
                operation_type=meta.get("operation_type"),
                common_patterns=meta.get("common_patterns"),
            )
    def register_enhanced_function(self, 
                                  func: Callable, 
                                  description: str, 
                                  parameters: Dict[str, Any],
                                  operation_type: Optional[str] = None,
                                  common_patterns: Optional[Dict[str, Any]] = None):
        """
        Register a function with enhanced metadata.
        
        This method wraps the standard register_function method and adds
        additional metadata for monitoring and discovery.
        
        Args:
            func: The function to register
            description: A description of what the function does
            parameters: JSON schema for the function parameters (either a dict or JSON string)
            operation_type: Type of operation (e.g., "calculation", "transformation")
            common_patterns: Common validation patterns used by this function
            
        Returns:
            The registered function (allows use as a decorator)
        """
        # Get the function name before wrapping
        func_name = func.__name__
        
        # Log start of registration process
        logger.info(f"Starting enhanced function registration for '{func_name}'", 
                   extra={
                       "service_name": self.service_name,
                       "function_name": func_name,
                       "operation_type": operation_type,
                       "has_common_patterns": bool(common_patterns)
                   })
        
        # Convert parameters to dict if it's a JSON string
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON schema string for function '{func_name}'")
                raise
        
        # Log function metadata
        logger.debug(f"Function metadata for '{func_name}'",
                    extra={
                        "description": description,
                        "parameters": parameters,
                        "operation_type": operation_type,
                        "common_patterns": common_patterns
                    })
        
        try:
            # Create the wrapper with the original function name
            logger.debug(f"Creating function wrapper for '{func_name}'")
            wrapped_func = self.function_wrapper(func_name)(func)
            wrapped_func.__name__ = func_name  # Preserve the original function name
            
            # Log wrapper creation success
            logger.debug(f"Successfully created wrapper for '{func_name}'")
            
            # Register the wrapped function with the base class
            logger.info(f"Registering wrapped function '{func_name}' with base class")
            result = self.register_function(
                func=wrapped_func,  # Register the wrapped function
                description=description,
                parameters=parameters,  # Pass as dict, register_function will handle serialization
                operation_type=operation_type,
                common_patterns=common_patterns
            )
            
            # Log successful registration
            logger.info(f"Successfully registered enhanced function '{func_name}'",
                       extra={
                           "service_name": self.service_name,
                           "function_name": func_name,
                           "registration_result": bool(result)
                       })
            
            return result
            
        except Exception as e:
            # Log registration failure with detailed error info
            logger.error(f"Failed to register enhanced function '{func_name}'",
                        extra={
                            "service_name": self.service_name,
                            "function_name": func_name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "traceback": logging.traceback.format_exc()
                        })
            raise
    
    def _publish_monitoring_event(self, event_type: str, function_name: str, 
                               call_data: Optional[Dict[str, Any]] = None,
                               result_data: Optional[Dict[str, Any]] = None,
                               status_data: Optional[Dict[str, Any]] = None,
                               metadata: Optional[Dict[str, Any]] = None,
                               request_info: Optional[Any] = None) -> None:
        """
        Publish a monitoring event.
        
        Args:
            event_type: Type of event (FUNCTION_DISCOVERY, FUNCTION_CALL, etc.)
            function_name: Name of the function involved
            call_data: Data about the function call (if applicable)
            result_data: Data about the function result (if applicable)
            status_data: Data about the function status (if applicable)
            metadata: Additional metadata about the event
            request_info: Request information containing client ID
        """
        event = dds.DynamicData(self.monitoring_type)
        event["event_id"] = str(uuid.uuid4())
        event["timestamp"] = int(time.time() * 1000)
        
        # Set event type and entity type
        event["event_type"] = EVENT_TYPE_MAP[event_type]
        
        # Set entity type based on event type and metadata
        if metadata and metadata.get("event") in ["node_join", "node_ready", "node_discovery"]:
            event["entity_type"] = ENTITY_TYPE_MAP["NODE"]
        else:
            event["entity_type"] = ENTITY_TYPE_MAP["FUNCTION"]
            
        event["entity_id"] = function_name
        
        # Build base metadata
        base_metadata = {
            "provider_id": str(self.participant.instance_handle),
            "client_id": str(request_info.publication_handle) if request_info else "unknown"
        }
        
        # Add event-specific metadata
        if event_type == "FUNCTION_DISCOVERY":
            base_metadata.update({
                "event": "discovery",
                "status": "available",
                "message": f"Function '{function_name}' available"
            })
        elif event_type == "FUNCTION_DISCOVERY_V2":
            base_metadata.update({
                "event": "discovery_v2",
                "status": "published",
                "message": f"Function '{function_name}' published"
            })
        elif event_type == "FUNCTION_CALL":
            call_id = f"call_{uuid.uuid4().hex[:8]}"
            base_metadata["call_id"] = call_id
            if request_info:
                # Store call_id for later correlation
                self._call_ids[str(request_info.publication_handle)] = call_id
            if call_data:
                args_str = ", ".join(f"{k}={v}" for k, v in call_data.items())
                base_metadata["message"] = f"Call received: {function_name}({args_str})"
        elif event_type == "FUNCTION_RESULT":
            if request_info:
                # Retrieve and remove call_id for this request
                call_id = self._call_ids.pop(str(request_info.publication_handle), None)
                if call_id:
                    base_metadata["call_id"] = call_id
            if result_data:
                result_str = str(result_data.get("result", "unknown"))
                base_metadata["message"] = f"Result sent: {function_name} = {result_str}"
        
        # Merge with provided metadata
        if metadata:
            base_metadata.update(metadata)
            
        event["metadata"] = json.dumps(base_metadata)
        if call_data:
            event["call_data"] = json.dumps(call_data)
        if result_data:
            event["result_data"] = json.dumps(result_data)
        if status_data:
            event["status_data"] = json.dumps(status_data)
        
        self.monitoring_writer.write(event)
        self.monitoring_writer.flush()

    def publish_component_lifecycle_event(self, 
                                       previous_state: str,
                                       new_state: str,
                                       reason: str = "",
                                       capabilities: str = "",
                                       chain_id: str = "",
                                       call_id: str = "",
                                       component_id: str = None,
                                       event_category: str = "",
                                       source_id: str = "",
                                       target_id: str = "",
                                       connection_type: str = ""):
        """
        Publish a component lifecycle event.
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

            # Create event
            event = dds.DynamicData(self.component_lifecycle_type)
            
            # Set component ID (use provided or app GUID)
            event["component_id"] = component_id if component_id else self.app_guid
            
            # Set component type (FUNCTION for calculator service)
            event["component_type"] = 3  # FUNCTION enum value
            
            # Set states
            event["previous_state"] = states[previous_state]
            event["new_state"] = states[new_state]
            
            # Set other fields
            event["timestamp"] = int(time.time() * 1000)
            event["reason"] = reason
            event["capabilities"] = capabilities
            event["chain_id"] = chain_id
            event["call_id"] = call_id
            
            # Set event category and related fields
            if event_category:
                event["event_category"] = event_categories[event_category]
                event["source_id"] = source_id if source_id else self.app_guid
                
                if event_category == "EDGE_DISCOVERY":
                    event["target_id"] = target_id
                    event["connection_type"] = connection_type if connection_type else "function_connection"
                elif event_category == "STATE_CHANGE":
                    event["target_id"] = source_id if source_id else self.app_guid
                    event["connection_type"] = ""
                else:
                    event["target_id"] = target_id if target_id else ""
                    event["connection_type"] = ""
            else:
                # Default to NODE_DISCOVERY if no category provided
                event["event_category"] = event_categories["NODE_DISCOVERY"]
                event["source_id"] = source_id if source_id else self.app_guid
                event["target_id"] = target_id if target_id else ""
                event["connection_type"] = ""

            # Write and flush the event
            self.component_lifecycle_writer.write(event)
            self.component_lifecycle_writer.flush()
            
        except Exception as e:
            logger.error(f"Error publishing component lifecycle event: {e}")
            logger.error(f"Event category was: {event_category}")
    
    def _advertise_functions(self):
        """
        Advertise registered functions to the function registry.
        
        This method:
        1. Iterates through all registered functions
        2. Builds metadata for each function
        3. Registers the function with the registry
        4. Publishes monitoring events for function discovery
        """
        if self._functions_advertised:
            logger.warning("===== DDS TRACE: Functions already advertised, skipping. =====")
            return

        logger.info("===== DDS TRACE: Starting function advertisement process... =====")

        # Get total number of functions for tracking first/last
        total_functions = len(self.functions)
        logger.info(f"===== DDS TRACE: Found {total_functions} functions to advertise. =====")

        # Publish initial node join event (both old and new monitoring)
        self._publish_monitoring_event(
            event_type="FUNCTION_STATUS",
            function_name=self.service_name,
            metadata={
                "service": self.__class__.__name__,
                "provider_id": self.app_guid,
                "message": f"Function app (id={self.app_guid}) joined domain",
                "event": "node_join"
            },
            status_data={"status": "joined", "state": "initializing"}
        )

        # First publish node discovery event
        self.publish_component_lifecycle_event(
            previous_state="DISCOVERING",
            new_state="DISCOVERING",
            reason=f"Function app {self.app_guid} discovered",
            capabilities=json.dumps(self.service_capabilities),
            event_category="NODE_DISCOVERY",
            source_id=self.app_guid,
            target_id=self.app_guid
        )

        # Then publish initialization event
        self.publish_component_lifecycle_event(
            previous_state="OFFLINE",
            new_state="JOINING",
            reason=f"Function app initialization started",
            capabilities=json.dumps(self.service_capabilities),
            event_category="AGENT_INIT",
            source_id=self.app_guid,
            target_id=self.app_guid
        )

        # Transition to discovering state
        self.publish_component_lifecycle_event(
            previous_state="JOINING",
            new_state="DISCOVERING",
            reason=f"Function app discovering functions",
            capabilities=json.dumps(self.service_capabilities),
            event_category="NODE_DISCOVERY",
            source_id=self.app_guid,
            target_id=self.app_guid
        )
        
        for i, (func_name, func_data) in enumerate(self.functions.items(), 1):
            logger.info(f"===== DDS TRACE: Preparing to advertise function {i}/{total_functions}: {func_name} =====")
            # Get schema from the function data
            schema = json.loads(func_data["tool"].function.parameters)
            
            # Get description
            description = func_data["tool"].function.description
            
            # Get capabilities
            capabilities = self.service_capabilities.copy()
            if func_data.get("operation_type"):
                capabilities.append(func_data["operation_type"])
            
            # Create capabilities dictionary with function name
            capabilities_dict = {
                "capabilities": capabilities,
                "function_name": func_name,  # Add function name
                "description": description
            }
            
            # Generate a random UUID for the function node
            function_id = str(uuid.uuid4())
            
            # Publish discovery event for each function
            self.publish_component_lifecycle_event(
                previous_state="DISCOVERING",
                new_state="DISCOVERING",
                reason=f"Function '{func_name}' available",
                capabilities=json.dumps(capabilities_dict),  # Use the dictionary
                component_id=function_id,
                event_category="NODE_DISCOVERY",
                source_id=function_id,
                target_id=function_id
            )

            # Publish edge discovery event between function app and function node
            edge_reason = f"provider={self.app_guid} client={function_id} function={function_id} name={func_name}"
            edge_capabilities = {
                "edge_type": "function_connection",
                "source_id": self.app_guid,
                "target_id": function_id,
                "function_name": func_name
            }
            
            # Publish edge discovery event using app_guid
            self.publish_component_lifecycle_event(
                previous_state="DISCOVERING",
                new_state="DISCOVERING",
                reason=edge_reason,
                capabilities=json.dumps(edge_capabilities),
                component_id=self.app_guid,
                event_category="EDGE_DISCOVERY",
                source_id=self.app_guid,
                target_id=function_id,
                connection_type="function_connection"
            )
            
            # Register with the function registry
            self.registry.register_function(
                func=func_data["implementation"],
                description=description,
                parameter_descriptions=schema,
                capabilities=capabilities,
                performance_metrics={"latency": "low"},
                security_requirements={"level": "public"}
            )
            
            logger.info(f"Advertised function: {func_name}")
            
            # If this is the first function, announce DDS connection
            if i == 1:
                logger.info(f"{self.__class__.__name__} connected to DDS")
            
            # If this is the last function, announce all functions published
            if i == total_functions:
                logger.info(f"All {self.__class__.__name__} functions published")
                # Publish final ready state
                self._publish_monitoring_event(
                    event_type="FUNCTION_STATUS",
                    function_name=self.service_name,
                    metadata={
                        "service": self.__class__.__name__,
                        "provider_id": self.app_guid,
                        "message": f"Function app (id={self.app_guid}) ready for calls",
                        "event": "node_ready"
                    },
                    status_data={"status": "ready", "state": "available"}
                )
                
                # Publish component lifecycle event for ready state
                self.publish_component_lifecycle_event(
                    previous_state="DISCOVERING",
                    new_state="READY",
                    reason=f"All {self.__class__.__name__} functions published and ready for calls",
                    capabilities=json.dumps(self.service_capabilities),
                    event_category="AGENT_READY",
                    source_id=self.app_guid,
                    target_id=self.app_guid
                )
        
        # Mark functions as advertised
        self._functions_advertised = True
        logger.info("===== DDS TRACE: Finished function advertisement process. =====")
    
    def publish_function_call_event(self, function_name: str, call_data: Dict[str, Any], request_info=None):
        """
        Publish a function call event.
        
        Args:
            function_name: Name of the function being called
            call_data: Data about the function call
            request_info: Request information containing client ID
        """
        self._publish_monitoring_event(
            event_type="FUNCTION_CALL",
            function_name=function_name,
            call_data=call_data,
            request_info=request_info
        )
    
    def publish_function_result_event(self, function_name: str, result_data: Dict[str, Any], request_info=None):
        """
        Publish a function result event.
        
        Args:
            function_name: Name of the function that produced the result
            result_data: Data about the function result
            request_info: Request information containing client ID
        """
        self._publish_monitoring_event(
            event_type="FUNCTION_RESULT",
            function_name=function_name,
            result_data=result_data,
            request_info=request_info
        )
    
    def publish_function_error_event(self, function_name: str, error: Exception, request_info=None):
        """
        Publish a function error event.
        
        Args:
            function_name: Name of the function that produced the error
            error: The exception that occurred
            request_info: Request information containing client ID
        """
        self._publish_monitoring_event(
            event_type="FUNCTION_STATUS",
            function_name=function_name,
            status_data={"error": str(error)},
            request_info=request_info
        )
    
    def function_wrapper(self, func_name: str):
        """
        Create a wrapper for a function that handles monitoring events.
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                # Extract request_info from kwargs
                request_info = kwargs.get('request_info')
                
                # Create call_data from args and kwargs
                call_data = {}
                # Add positional arguments (excluding self)
                if len(args) > 1:
                    func_params = func.__code__.co_varnames[1:func.__code__.co_argcount]
                    for i, param in enumerate(func_params):
                        if i < len(args) - 1:
                            call_data[param] = args[i + 1]
                
                # Add keyword arguments (excluding request_info)
                for k, v in kwargs.items():
                    if k != 'request_info':
                        call_data[k] = v
                
                try:
                    # Generate a unique chain ID for this call
                    chain_id = str(uuid.uuid4())
                    # Get the DDS RPC call ID from request_info
                    call_id = str(request_info.publication_handle) if request_info else str(uuid.uuid4())
                    
                    # Publish state change to BUSY with chain correlation
                    self.publish_component_lifecycle_event(
                        previous_state="READY",
                        new_state="BUSY",
                        reason=f"Processing function call: {func_name}({', '.join(f'{k}={v}' for k,v in call_data.items())})",
                        capabilities=json.dumps(self.service_capabilities),
                        chain_id=chain_id,
                        call_id=call_id
                    )
                    
                    # Create and publish chain event for function call start
                    chain_event = dds.DynamicData(self.chain_event_type)
                    chain_event["chain_id"] = chain_id
                    chain_event["call_id"] = call_id
                    chain_event["interface_id"] = str(request_info.publication_handle) if request_info else ""
                    chain_event["primary_agent_id"] = ""  # Set if using agents
                    chain_event["specialized_agent_ids"] = ""  # Set if using specialized agents
                    chain_event["function_id"] = func_name  # Use actual function name instead of app GUID
                    chain_event["query_id"] = str(uuid.uuid4())
                    chain_event["timestamp"] = int(time.time() * 1000)
                    chain_event["event_type"] = "CALL_START"
                    chain_event["source_id"] = str(request_info.publication_handle) if request_info else "unknown"
                    chain_event["target_id"] = self.app_guid
                    chain_event["status"] = 0  # 0 = Started
                    
                    self.chain_event_writer.write(chain_event)
                    self.chain_event_writer.flush()
                    
                    # Call the function
                    result = func(*args, **kwargs)
                    
                    # Create and publish chain event for function call completion
                    chain_event = dds.DynamicData(self.chain_event_type)
                    chain_event["chain_id"] = chain_id  # Same chain_id as start event
                    chain_event["call_id"] = call_id
                    chain_event["interface_id"] = str(request_info.publication_handle) if request_info else ""
                    chain_event["primary_agent_id"] = ""
                    chain_event["specialized_agent_ids"] = ""
                    chain_event["function_id"] = func_name  # Use actual function name instead of app GUID
                    chain_event["query_id"] = str(uuid.uuid4())
                    chain_event["timestamp"] = int(time.time() * 1000)
                    chain_event["event_type"] = "CALL_COMPLETE"
                    chain_event["source_id"] = self.app_guid
                    chain_event["target_id"] = str(request_info.publication_handle) if request_info else "unknown"
                    chain_event["status"] = 1  # 1 = Completed
                    
                    self.chain_event_writer.write(chain_event)
                    self.chain_event_writer.flush()
                    
                    # Publish state change back to READY with chain correlation
                    self.publish_component_lifecycle_event(
                        previous_state="BUSY",
                        new_state="READY",
                        reason=f"Completed function call: {func_name} = {result}",
                        capabilities=json.dumps(self.service_capabilities),
                        chain_id=chain_id,
                        call_id=call_id
                    )
                    
                    return result
                except Exception as e:
                    # Create and publish chain event for function call error
                    chain_event = dds.DynamicData(self.chain_event_type)
                    chain_event["chain_id"] = chain_id
                    chain_event["call_id"] = call_id
                    chain_event["interface_id"] = str(request_info.publication_handle) if request_info else ""
                    chain_event["primary_agent_id"] = ""
                    chain_event["specialized_agent_ids"] = ""
                    chain_event["function_id"] = func_name  # Use actual function name instead of app GUID
                    chain_event["query_id"] = str(uuid.uuid4())
                    chain_event["timestamp"] = int(time.time() * 1000)
                    chain_event["event_type"] = "CALL_ERROR"
                    chain_event["source_id"] = self.app_guid
                    chain_event["target_id"] = str(request_info.publication_handle) if request_info else "unknown"
                    chain_event["status"] = 2  # 2 = Error
                    
                    self.chain_event_writer.write(chain_event)
                    self.chain_event_writer.flush()
                    
                    # Publish state change to DEGRADED with chain correlation
                    self.publish_component_lifecycle_event(
                        previous_state="BUSY",
                        new_state="DEGRADED",
                        reason=f"Error in function {func_name}: {str(e)}",
                        capabilities=json.dumps(self.service_capabilities),
                        chain_id=chain_id,
                        call_id=call_id
                    )
                    raise
            
            return wrapper
        
        return decorator
    
    async def run(self):
        """
        Run the service and handle incoming requests.
        
        This method:
        1. Advertises functions if they haven't been advertised yet
        2. Calls the base class run method
        3. Ensures proper cleanup of resources
        """
        # Advertise functions if they haven't been advertised yet
        if not self._functions_advertised:
            self._advertise_functions()
            
        try:
            await super().run()
        finally:
            # Clean up registry
            if hasattr(self, 'registry'):
                self.registry.close()

    def handle_function_discovery(self, function_name: str, metadata: Dict[str, Any], status_data: Dict[str, Any]):
        """
        Handle function discovery events from the registry.
        
        Args:
            function_name: Name of the discovered function
            metadata: Metadata about the function and discovery event
            status_data: Status information about the function
        """
        function_id = metadata.get('function_id', str(uuid.uuid4()))

        # For function providers (like calculator service)
        if self.service_name.lower() in ["calculator", "calculatorservice", "textprocessor", "textprocessorservice"]:
            # Only handle our own functions
            if function_id in self.registry.functions:
                # First, publish the function availability event with the function's ID
                reason = f"Function '{function_name}' (id={function_id}) [Function '{function_name}' available]"

                # Publish new monitoring event for function availability using function_id
                self.publish_component_lifecycle_event(
                    previous_state="DISCOVERING",
                    new_state="DISCOVERING",
                    reason=reason,
                    capabilities=json.dumps(self.service_capabilities),
                    component_id=function_id,
                    event_category="NODE_DISCOVERY",
                    source_id=function_id,
                    target_id=function_id
                )
                
                # Then create an edge between the function and its hosting app
                edge_reason = f"provider={self.app_guid} client={function_id} function={function_id} name={function_name}"
                
                # Publish edge discovery event using app_guid
                self.publish_component_lifecycle_event(
                    previous_state="DISCOVERING",
                    new_state="DISCOVERING",
                    reason=edge_reason,
                    capabilities=json.dumps(self.service_capabilities),
                    component_id=self.app_guid,
                    event_category="EDGE_DISCOVERY",
                    source_id=self.app_guid,
                    target_id=function_id,
                    connection_type="function_connection"
                )
            return

        # For agents and other services that discover external functions
        if function_id not in self.registry.functions:  # Only handle functions we don't own
            self.last_discovered_function = function_name
            # Format the reason string for external edge discovery
            reason = f"provider={metadata['provider_id']} client={metadata['client_id']} function={function_id} name={function_name}"
            
            # Publish edge discovery event
            self.publish_component_lifecycle_event(
                previous_state="DISCOVERING",
                new_state="DISCOVERING",
                reason=reason,
                capabilities=json.dumps(self.service_capabilities),
                component_id=metadata['client_id'],  # Use client_id for the edge event
                event_category="EDGE_DISCOVERY",
                source_id=self.app_guid,
                target_id=metadata['client_id'],
                connection_type="function_connection"
            )

    def handle_function_removal(self, function_name: str, metadata: Dict[str, Any]):
        """
        Handle function removal events from the registry.
        
        Args:
            function_name: Name of the removed function
            metadata: Metadata about the function and removal event
        """
        self._publish_monitoring_event(
            event_type="FUNCTION_STATUS",
            function_name=function_name,
            metadata=metadata,
            status_data={"status": "removed", "state": "unavailable"}
        )

    def close(self):
        """Clean up all service resources"""
        logger.info(f"Closing {self.service_name}...")
        
        # Close registry if it exists
        if hasattr(self, 'registry'):
            self.registry.close()
            
        # Close base class resources
        super().close()
            
        logger.info(f"{self.service_name} closed successfully")

# Example of how to use the enhanced service base
if __name__ == "__main__":
    # This is just an example and won't be executed when imported
    class ExampleService(EnhancedServiceBase):
        def __init__(self):
            super().__init__(service_name="ExampleService", capabilities=["example", "demo"])
            
            # Register functions
            self.register_enhanced_function(
                self.example_function,
                "Example function",
                {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text input"}
                    },
                    "required": ["text"]
                },
                operation_type="example"
            )
            
            # Advertise functions
            self._advertise_functions()
        
        def example_function(self, text: str, request_info=None) -> Dict[str, Any]:
            # Function implementation
            return {"result": text.upper()}
    
    # Run the example service
    service = ExampleService()
    asyncio.run(service.run()) 