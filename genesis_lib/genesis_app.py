#!/usr/bin/env python3

import logging
import time
from typing import Dict, List, Any, Optional, Callable
import uuid
import rti.connextdds as dds
from genesis_lib.function_discovery import FunctionRegistry, FunctionInfo
from genesis_lib.logging_config import configure_genesis_logging
from .function_patterns import SuccessPattern, FailurePattern, pattern_registry
import os
import traceback
from genesis_lib.utils import get_datamodel_path
import asyncio

# Configure logging
logger = configure_genesis_logging(
    logger_name="genesis_app",
    source_name="GenesisApp",
    log_level=logging.INFO
)

class GenesisApp:
    """
    Base class for Genesis applications that provides function registration
    and discovery capabilities.
    
    This class integrates with the FunctionRegistry to provide a clean
    interface for registering functions from Genesis applications.
    """
    
    def __init__(self, participant=None, domain_id=0, preferred_name="DefaultAgent", agent_id=None):
        """
        Initialize the Genesis application.
        
        Args:
            participant: DDS participant (if None, will create one)
            domain_id: DDS domain ID
            preferred_name: Preferred name for this application instance
            agent_id: Optional UUID for the agent (if None, will generate one)
        """
        # Generate or use provided agent ID
        self.agent_id = agent_id or str(uuid.uuid4())
        self.preferred_name = preferred_name
        
        # Initialize DDS participant
        if participant is None:
            participant_qos = dds.QosProvider.default.participant_qos
            self.participant = dds.DomainParticipant(domain_id, qos=participant_qos)
        else:
            self.participant = participant
            
        # Store DDS GUID
        self.dds_guid = str(self.participant.instance_handle)
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.registration_type = self.type_provider.type("genesis_lib", "genesis_agent_registration_announce")
        
        # Create topics
        self.registration_topic = dds.DynamicData.Topic(
            self.participant, 
            "GenesisRegistration", 
            self.registration_type
        )
        
        # Create publisher and subscriber with QoS
        self.publisher = dds.Publisher(
            self.participant,
            qos=dds.QosProvider.default.publisher_qos
        )
        self.subscriber = dds.Subscriber(
            self.participant,
            qos=dds.QosProvider.default.subscriber_qos
        )
        
        # Create DataWriter with QoS
        writer_qos = dds.QosProvider.default.datawriter_qos
        writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        writer_qos.history.kind = dds.HistoryKind.KEEP_LAST
        writer_qos.history.depth = 500
        writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        writer_qos.liveliness.kind = dds.LivelinessKind.AUTOMATIC
        writer_qos.liveliness.lease_duration = dds.Duration(seconds=2)
        writer_qos.ownership.kind = dds.OwnershipKind.SHARED
        
        # Initialize function registry and pattern registry
        self.function_registry = FunctionRegistry(self.participant, domain_id)
        self.pattern_registry = pattern_registry
        
        # Register built-in functions
        self._register_builtin_functions()
        
        logger.info(f"GenesisApp initialized with agent_id={self.agent_id}, dds_guid={self.dds_guid}")

    async def close(self):
        """Close all DDS entities and cleanup resources"""
        if hasattr(self, '_closed') and self._closed:
            logger.info(f"GenesisApp {self.agent_id} is already closed")
            return

        try:
            # Close DDS entities in reverse order of creation, but keep registration writer until last
            resources_to_close = ['function_registry', 'registration_reader', 'registration_topic', 
                                'publisher', 'subscriber', 'participant']
            
            # First close everything except registration writer
            for resource in resources_to_close:
                if hasattr(self, resource):
                    try:
                        resource_obj = getattr(self, resource)
                        if hasattr(resource_obj, 'close') and not getattr(resource_obj, '_closed', False):
                            if asyncio.iscoroutinefunction(resource_obj.close):
                                await resource_obj.close()
                            else:
                                resource_obj.close()
                    except Exception as e:
                        # Only log as warning if the error is not about being already closed
                        if "already closed" not in str(e).lower():
                            logger.warning(f"Error closing {resource}: {str(e)}")
            
            # Mark as closed
            self._closed = True
            logger.info(f"GenesisApp {self.agent_id} closed successfully")
        except Exception as e:
            logger.error(f"Error closing GenesisApp: {str(e)}")
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

    def _register_builtin_functions(self):
        """Register any built-in functions for this application"""
        # Override this method in subclasses to register built-in functions
        pass

    def execute_function(self, function_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a registered function with error pattern checking.
        
        Args:
            function_id: ID of function to execute
            parameters: Function parameters
            
        Returns:
            Dictionary containing result or error information
        """
        try:
            # Execute the function
            result = super().execute_function(function_id, parameters)
            
            # Check result against patterns
            is_success, error_code, recovery_hint = self.pattern_registry.check_result(function_id, result)
            
            if is_success:
                return {
                    "status": "success",
                    "result": result
                }
            else:
                return {
                    "status": "error",
                    "error_code": error_code,
                    "message": str(result),
                    "recovery_hint": recovery_hint
                }
                
        except Exception as e:
            # Check if exception matches any failure patterns
            is_success, error_code, recovery_hint = self.pattern_registry.check_result(function_id, e)
            
            return {
                "status": "error",
                "error_code": error_code or "UNKNOWN_ERROR",
                "message": str(e),
                "recovery_hint": recovery_hint
            } 