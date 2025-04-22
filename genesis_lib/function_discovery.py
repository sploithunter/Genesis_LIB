#!/usr/bin/env python3

import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
import json
from genesis_lib.logging_config import configure_genesis_logging
import uuid
import time
import rti.connextdds as dds
import rti.rpc as rpc
import re
import os
from genesis_lib.utils import get_datamodel_path

# Configure logging
logger = logging.getLogger("function_discovery")

@dataclass
class FunctionInfo:
    """Information about a registered function"""
    function_id: str
    name: str
    description: str
    function: Callable
    schema: Dict[str, Any]
    categories: List[str]
    performance_metrics: Dict[str, Any]
    security_requirements: Dict[str, Any]
    match_info: Optional[Dict[str, Any]] = None
    classification: Optional[Dict[str, Any]] = None
    operation_type: Optional[str] = None  # One of: transformation, analysis, generation, calculation
    common_patterns: Optional[Dict[str, Any]] = None  # Common validation patterns used by this function

    def get_validation_patterns(self) -> Dict[str, Any]:
        """
        Get validation patterns for this function.
        
        Returns:
            Dictionary of validation patterns
        """
        if not self.common_patterns:
            return {}
            
        # Common validation patterns
        patterns = {
            "text": {
                "min_length": 1,
                "max_length": None,
                "pattern": None
            },
            "letter": {
                "min_length": 1,
                "max_length": 1,
                "pattern": "^[a-zA-Z]$"
            },
            "count": {
                "minimum": 0,
                "maximum": 1000
            },
            "number": {
                "minimum": None,
                "maximum": None
            }
        }
        
        # Update with function-specific patterns
        for pattern_type, pattern in self.common_patterns.items():
            if pattern_type in patterns:
                patterns[pattern_type].update(pattern)
                
        return patterns

    def validate_input(self, parameter_name: str, value: Any) -> None:
        """
        Validate input using common patterns.
        
        Args:
            parameter_name: Name of the parameter to validate
            value: Value to validate
            
        Raises:
            ValueError: If validation fails
        """
        if not self.common_patterns or parameter_name not in self.common_patterns:
            return
            
        pattern = self.common_patterns[parameter_name]
        pattern_type = pattern.get("type", "text")
        
        if pattern_type == "text":
            if not isinstance(value, str):
                raise ValueError(f"{parameter_name} must be a string")
                
            if pattern.get("min_length") and len(value) < pattern["min_length"]:
                raise ValueError(f"{parameter_name} must be at least {pattern['min_length']} character(s)")
                
            if pattern.get("max_length") and len(value) > pattern["max_length"]:
                raise ValueError(f"{parameter_name} cannot exceed {pattern['max_length']} character(s)")
                
            if pattern.get("pattern") and not re.match(pattern["pattern"], value):
                raise ValueError(f"{parameter_name} must match pattern: {pattern['pattern']}")
                
        elif pattern_type in ["number", "integer"]:
            if not isinstance(value, (int, float)):
                raise ValueError(f"{parameter_name} must be a number")
                
            if pattern.get("minimum") is not None and value < pattern["minimum"]:
                raise ValueError(f"{parameter_name} must be at least {pattern['minimum']}")
                
            if pattern.get("maximum") is not None and value > pattern["maximum"]:
                raise ValueError(f"{parameter_name} cannot exceed {pattern['maximum']}")

class FunctionMatcher:
    """Matches functions based on LLM analysis of requirements and available functions"""
    
    def __init__(self, llm_client=None):
        """Initialize the matcher with optional LLM client"""
        self.logger = logging.getLogger("function_matcher")
        self.llm_client = llm_client
    
    def find_matching_functions(self,
                              user_request: str,
                              available_functions: List[Dict[str, Any]],
                              min_similarity: float = 0.7) -> List[Dict[str, Any]]:
        """
        Find functions that match the user's request using LLM analysis.
        
        Args:
            user_request: The user's natural language request
            available_functions: List of available function metadata
            min_similarity: Minimum similarity score (0-1)
            
        Returns:
            List of matching function metadata with relevance scores
        """
        if not self.llm_client:
            self.logger.warning("No LLM client provided, falling back to basic matching")
            return self._fallback_matching(user_request, available_functions)
        
        # Create prompt for LLM
        prompt = f"""Given the following user request:

{user_request}

And the following functions:

{json.dumps([{
    "function_name": f["name"],
    "function_description": f.get("description", "")
} for f in available_functions], indent=2)}

For each relevant function, return a JSON array where each object has:
- function_name: The name of the matching function
- domain: The primary domain/category this function belongs to (e.g., "weather", "mathematics")
- operation_type: The type of operation this function performs (e.g., "lookup", "calculation")

Only include functions that are actually relevant to the request. Do not return anything else."""

        # Log the prompt being sent to the LLM
        self.logger.info(
            "LLM Classification Prompt",
            extra={
                "user_request": user_request,
                "prompt": prompt,
                "available_functions": [f["name"] for f in available_functions]
            }
        )

        try:
            # Get LLM response
            response = self.llm_client.generate_response(prompt, "function_matching")
            
            # Log the raw LLM response for monitoring
            self.logger.info(
                "LLM Function Classification Response",
                extra={
                    "user_request": user_request,
                    "raw_response": response[0],
                    "response_status": response[1],
                    "available_functions": [f["name"] for f in available_functions]
                }
            )
            
            # Parse response
            matches = json.loads(response[0])
            
            # Convert matches to full metadata
            result = []
            for match in matches:
                func = next((f for f in available_functions if f["name"] == match["function_name"]), None)
                if func:
                    # Add match info
                    func["match_info"] = {
                        "relevance_score": 1.0,  # Since we're just doing exact matches
                        "explanation": "Function name matched by LLM",
                        "inferred_params": {},  # Parameter inference happens later
                        "considerations": [],
                        "domain": match.get("domain", "unknown"),
                        "operation_type": match.get("operation_type", "unknown")
                    }
                    result.append(func)
            
            # Log the processed matches for monitoring
            self.logger.info(
                "Processed Function Matches",
                extra={
                    "user_request": user_request,
                    "matches": result,
                    "min_similarity": min_similarity
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Error in LLM-based matching",
                extra={
                    "user_request": user_request,
                    "error": str(e),
                    "available_functions": [f["name"] for f in available_functions]
                }
            )
            return self._fallback_matching(user_request, available_functions)
    
    def _prepare_function_descriptions(self, functions: List[Dict[str, Any]]) -> str:
        """Prepare function descriptions for LLM analysis"""
        descriptions = []
        for func in functions:
            desc = f"Function: {func['name']}\n"
            desc += f"Description: {func.get('description', '')}\n"
            desc += "Parameters:\n"
            
            # Add parameter descriptions
            if "parameter_schema" in func and "properties" in func["parameter_schema"]:
                for param_name, param_schema in func["parameter_schema"]["properties"].items():
                    desc += f"- {param_name}: {param_schema.get('description', param_schema.get('type', 'unknown'))}"
                    if param_schema.get("required", False):
                        desc += " (required)"
                    desc += "\n"
            
            # Add performance and security info if available
            if "performance_metrics" in func:
                desc += "Performance:\n"
                for metric, value in func["performance_metrics"].items():
                    desc += f"- {metric}: {value}\n"
            
            if "security_requirements" in func:
                desc += "Security:\n"
                for req, value in func["security_requirements"].items():
                    desc += f"- {req}: {value}\n"
            
            descriptions.append(desc)
        
        return "\n".join(descriptions)
    
    def _convert_matches_to_metadata(self, 
                                   matches: List[Dict[str, Any]], 
                                   available_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert LLM matches to function metadata format"""
        result = []
        for match in matches:
            # Find the original function metadata
            func = next((f for f in available_functions if f["name"] == match["function_name"]), None)
            if func:
                # Add match information
                func["match_info"] = {
                    "relevance_score": match["relevance_score"],
                    "explanation": match["explanation"],
                    "inferred_params": match["inferred_params"],
                    "considerations": match["considerations"],
                    "domain": match.get("domain", "unknown"),
                    "operation_type": match.get("operation_type", "unknown")
                }
                result.append(func)
        return result
    
    def _fallback_matching(self, user_request: str, available_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback to basic matching if LLM is not available"""
        # Simple text-based matching as fallback
        matches = []
        request_lower = user_request.lower()
        request_words = set(request_lower.split())
        
        for func in available_functions:
            # Check function name and description
            name_match = func["name"].lower() in request_lower
            desc_match = func.get("description", "").lower() in request_lower
            
            # Check for word matches in both name and description
            func_name_words = set(func["name"].lower().split())
            func_desc_words = set(func.get("description", "").lower().split())
            
            # Calculate word overlap
            name_word_overlap = bool(func_name_words & request_words)
            desc_word_overlap = bool(func_desc_words & request_words)
            
            if name_match or desc_match or name_word_overlap or desc_word_overlap:
                # Calculate a simple relevance score based on matches
                if name_match and desc_match:
                    relevance_score = 0.5
                elif name_match or desc_match:
                    relevance_score = 0.5
                elif name_word_overlap and desc_word_overlap:
                    relevance_score = 0.5
                elif name_word_overlap or desc_word_overlap:
                    relevance_score = 0.4
                else:
                    relevance_score = 0.3
                
                # Try to infer parameters from the request
                inferred_params = {}
                if "parameter_schema" in func and "properties" in func["parameter_schema"]:
                    for param_name, param_schema in func["parameter_schema"]["properties"].items():
                        # Look for parameter values in the request
                        param_desc = param_schema.get("description", "").lower()
                        if param_desc in request_lower:
                            # Extract the value after the parameter description
                            value_start = request_lower.find(param_desc) + len(param_desc)
                            value_end = request_lower.find(" ", value_start)
                            if value_end == -1:
                                value_end = len(request_lower)
                            value = request_lower[value_start:value_end].strip()
                            if value:
                                inferred_params[param_name] = value
                
                # Log the fallback matching details
                self.logger.info(
                    "Fallback Matching Details",
                    extra={
                        "user_request": user_request,
                        "function_name": func["name"],
                        "name_match": name_match,
                        "desc_match": desc_match,
                        "name_word_overlap": name_word_overlap,
                        "desc_word_overlap": desc_word_overlap,
                        "relevance_score": relevance_score,
                        "inferred_params": inferred_params
                    }
                )
                
                func["match_info"] = {
                    "relevance_score": relevance_score,
                    "explanation": "Basic text matching",
                    "inferred_params": inferred_params,
                    "considerations": ["Using basic text matching - results may be less accurate"],
                    "domain": "unknown",
                    "operation_type": "unknown"
                }
                matches.append(func)
        
        # Sort matches by relevance score
        matches.sort(key=lambda x: x["match_info"]["relevance_score"], reverse=True)
        
        return matches 

class FunctionRegistry:
    """
    Registry for functions that can be called by the agent.
    
    This implementation supports DDS-based distributed function discovery
    and execution, where functions can be provided by:
    1. Other agents with specific expertise
    2. Traditional ML models wrapped as function providers
    3. Planning agents for complex task decomposition
    4. Simple procedural code exposed as functions
    
    The distributed implementation uses DDS topics for:
    - Function capability advertisement
    - Function discovery and matching
    - Function execution requests via DDS RPC
    - Function execution results via DDS RPC
    """
    
    def __init__(self, participant=None, domain_id=0):
        """
        Initialize the function registry.
        
        Args:
            participant: DDS participant (if None, will create one)
            domain_id: DDS domain ID
        """
        self.functions = {}  # Dict[str, FunctionInfo]
        self.function_by_name = {}  # Dict[str, str] mapping names to IDs
        self.function_by_category = {}  # Dict[str, List[str]] mapping categories to IDs
        self.discovered_functions = {}  # Dict[str, Dict] of functions from other providers
        self.service_base = None  # Reference to EnhancedServiceBase
        
        # Initialize function matcher with LLM support
        self.matcher = FunctionMatcher()
        
        # Create DDS participant if not provided
        if participant is None:
            participant = dds.DomainParticipant(domain_id)
        
        # Store participant reference
        self.participant = participant
        
        # Create subscriber
        self.subscriber = dds.Subscriber(participant)
        
        # Create publisher
        self.publisher = dds.Publisher(participant)
        
        # Get types from XML
        config_path = get_datamodel_path()
        self.type_provider = dds.QosProvider(config_path)
        self.capability_type = self.type_provider.type("genesis_lib", "FunctionCapability")
        self.execution_request_type = self.type_provider.type("genesis_lib", "FunctionExecutionRequest")
        self.execution_reply_type = self.type_provider.type("genesis_lib", "FunctionExecutionReply")
        
        # Create topics
        self.capability_topic = dds.DynamicData.Topic(
            participant,
            "FunctionCapability",
            self.capability_type
        )
        
        # Create DataReader for capability discovery
        reader_qos = dds.QosProvider.default.datareader_qos
        reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        reader_qos.history.kind = dds.HistoryKind.KEEP_LAST
        reader_qos.history.depth = 500
        reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        reader_qos.liveliness.kind = dds.LivelinessKind.AUTOMATIC
        reader_qos.liveliness.lease_duration = dds.Duration(seconds=2)
        
        self.capability_listener = FunctionCapabilityListener(self)
        self.capability_reader = dds.DynamicData.DataReader(
            topic=self.capability_topic,
            qos=reader_qos,
            listener=self.capability_listener,
            subscriber=self.subscriber,
            mask=dds.StatusMask.ALL
        )
        
        # Create DataWriter for capability advertisement
        writer_qos = dds.QosProvider.default.datawriter_qos
        writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        writer_qos.history.kind = dds.HistoryKind.KEEP_LAST
        writer_qos.history.depth = 500
        writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        writer_qos.liveliness.kind = dds.LivelinessKind.AUTOMATIC
        writer_qos.liveliness.lease_duration = dds.Duration(seconds=2)
        
        self.capability_writer = dds.DynamicData.DataWriter(
            pub=self.publisher,
            topic=self.capability_topic,
            qos=writer_qos,
            mask=dds.StatusMask.ALL
        )
        
        # Create RPC client for function execution
        self.execution_client = rpc.Requester(
            request_type=self.execution_request_type,
            reply_type=self.execution_reply_type,
            participant=participant,
            service_name="FunctionExecution"
        )
    
    def register_function(self, 
                         func: Callable,
                         description: str,
                         parameter_descriptions: Dict[str, Any],
                         capabilities: List[str] = None,
                         performance_metrics: Dict[str, Any] = None,
                         security_requirements: Dict[str, Any] = None) -> str:
        """
        Register a function with the registry.
        
        Args:
            func: The function to register
            description: Human-readable description of the function
            parameter_descriptions: JSON Schema for function parameters
            capabilities: List of capability tags
            performance_metrics: Performance characteristics
            security_requirements: Security requirements
            
        Returns:
            Function ID of the registered function
        """
        # Generate function ID
        function_id = str(uuid.uuid4())
        
        # Log start of registration process
        logger.info(f"Starting function registration in FunctionRegistry",
                   extra={
                       "function_name": func.__name__,
                       "function_id": function_id,
                       "capabilities": capabilities,
                       "has_performance_metrics": bool(performance_metrics),
                       "has_security_requirements": bool(security_requirements)
                   })
        
        # Log detailed function information
        logger.debug(f"Detailed function registration information",
                    extra={
                        "function_name": func.__name__,
                        "function_id": function_id,
                        "description": description,
                        "parameter_schema": parameter_descriptions,
                        "capabilities": capabilities,
                        "performance_metrics": performance_metrics,
                        "security_requirements": security_requirements
                    })
        
        try:
            # Create function info
            logger.debug(f"Creating FunctionInfo object for '{func.__name__}'")
            function_info = FunctionInfo(
                function_id=function_id,
                name=func.__name__,
                description=description,
                function=func,
                schema=parameter_descriptions,
                categories=capabilities or [],
                performance_metrics=performance_metrics or {},
                security_requirements=security_requirements or {}
            )
            
            # Store function info
            logger.debug(f"Storing function info for '{func.__name__}' in registry")
            self.functions[function_id] = function_info
            self.function_by_name[function_info.name] = function_id
            
            # Update category index
            logger.debug(f"Updating category index for '{func.__name__}'")
            for category in function_info.categories:
                if category not in self.function_by_category:
                    self.function_by_category[category] = []
                self.function_by_category[category].append(function_id)
                logger.debug(f"Added function '{func.__name__}' to category '{category}'")
            
            # Advertise function capability
            logger.info(f"Advertising function capability for '{func.__name__}'")
            self._advertise_function(function_info)
            
            # Log successful registration
            logger.info(f"Successfully registered function '{func.__name__}'",
                       extra={
                           "function_id": function_id,
                           "function_name": func.__name__,
                           "categories": list(function_info.categories),
                           "registered_categories_count": len(function_info.categories)
                       })
            
            return function_id
            
        except Exception as e:
            # Log registration failure with detailed error info
            logger.error(f"Failed to register function '{func.__name__}'",
                        extra={
                            "function_id": function_id,
                            "function_name": func.__name__,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "traceback": logging.traceback.format_exc()
                        })
            raise
    
    def find_matching_functions(self,
                              user_request: str,
                              min_similarity: float = 0.7) -> List[FunctionInfo]:
        """
        Find functions that match the user's request.
        
        Args:
            user_request: The user's natural language request
            min_similarity: Minimum similarity score (0-1)
            
        Returns:
            List of matching FunctionInfo objects
        """
        # Convert functions to format expected by matcher
        available_functions = [
            {
                "name": func.name,
                "description": func.description,
                "parameter_schema": func.schema,
                "capabilities": func.categories,
                "performance_metrics": func.performance_metrics,
                "security_requirements": func.security_requirements
            }
            for func in self.functions.values()
        ]
        
        # Find matches using the matcher
        matches = self.matcher.find_matching_functions(
            user_request=user_request,
            available_functions=available_functions,
            min_similarity=min_similarity
        )
        
        # Convert matches back to FunctionInfo objects
        result = []
        for match in matches:
            function_id = self.function_by_name.get(match["name"])
            if function_id and function_id in self.functions:
                func_info = self.functions[function_id]
                func_info.match_info = match.get("match_info", {})
                result.append(func_info)
        
        return result
    
    def _advertise_function(self, function_info: FunctionInfo):
        """Advertise function capability via DDS"""
        capability = dds.DynamicData(self.capability_type)
        capability['function_id'] = function_info.function_id
        capability['name'] = function_info.name
        capability['description'] = function_info.description
        capability['provider_id'] = str(self.capability_writer.instance_handle)  # Use DataWriter GUID
        capability['parameter_schema'] = json.dumps(function_info.schema)
        capability['capabilities'] = json.dumps(function_info.categories)
        capability['performance_metrics'] = json.dumps(function_info.performance_metrics)
        capability['security_requirements'] = json.dumps(function_info.security_requirements)
        capability['classification'] = json.dumps(function_info.classification or {})
        capability['last_seen'] = int(time.time() * 1000)
        
        self.capability_writer.write(capability)
        self.capability_writer.flush()
    
    def handle_capability_advertisement(self, capability: dds.DynamicData, info: dds.SampleInfo):
        """Handle incoming function capability advertisement."""
        function_id = capability['function_id']
        provider_id = str(info.publication_handle)  # Use DataWriter GUID from the remote publisher
        client_id = str(self.capability_writer.instance_handle)  # Use our DataWriter GUID
        
        # Determine if we're the provider or client
        is_provider = function_id in self.functions
        role = "PROVIDER" if is_provider else "CLIENT"
        
       # print(f"DEBUG: {role} side processing function_id={function_id}, provider={provider_id}, client={client_id}")
        
        # Skip if this is our own function - we don't need to discover it
        if is_provider:
            return
        
        # Check if we've already discovered this function from this provider
        if function_id in self.discovered_functions:
            existing_info = self.discovered_functions[function_id]
            if existing_info['provider_id'] == provider_id:
                # Already discovered from this provider, skip
                return
        
        # Extract schema from capability
        try:
            schema = json.loads(capability['parameter_schema'])
        except (json.JSONDecodeError, KeyError):
            schema = {}  # Default to empty schema if not found or invalid
            
        # Store discovered function information - only for functions we don't own
        self.discovered_functions[function_id] = {
            'name': capability['name'],
            'description': capability['description'],
            'provider_id': provider_id,  # Use DataWriter GUID
            'discoverer_id': client_id,  # Use DataWriter GUID
            'schema': schema,
            'capability': capability
        }
        
        # Build metadata for service base
        metadata = {
            "function_name": capability['name'],
            "provider_id": provider_id,
            "client_id": client_id,
            "function_id": function_id,
            "description": capability['description'],
            "message": f"provider={provider_id}, client={client_id} function={function_id}",
            "role": role.lower()
        }
        
        # Notify EnhancedServiceBase about the discovery
        if self.service_base is not None:
            self.service_base.handle_function_discovery(
                function_name=capability['name'],
                metadata=metadata,
                status_data={"status": "discovered", "state": "available"}
            )
    
    def handle_capability_removal(self, reader: dds.DynamicData.DataReader):
        """Handle removal of function capabilities when a provider goes offline"""
        try:
            samples = reader.take()
            for data, info in samples:
                if data and info.state.instance_state != dds.InstanceState.ALIVE:
                    function_id = data['function_id']
                    if function_id in self.discovered_functions:
                        function_info = self.discovered_functions[function_id]
                        
                        # Build metadata for service base
                        metadata = {
                            "function_id": function_id,
                            "function_name": function_info['name'],
                            "provider_id": function_info['provider_id']
                        }
                        
                        # Notify EnhancedServiceBase about the removal
                        if self.service_base is not None:
                            self.service_base.handle_function_removal(
                                function_name=function_info['name'],
                                metadata=metadata
                            )
                        
                        logger.info(f"Removing function {function_id} due to provider going offline")
                        del self.discovered_functions[function_id]
        except Exception as e:
            logger.error(f"Error handling capability removal: {e}")
    
    def get_function_by_id(self, function_id: str) -> Optional[FunctionInfo]:
        """
        Get function by ID.
        
        Args:
            function_id: ID of function to retrieve
            
        Returns:
            FunctionInfo if found, None otherwise
        """
        return self.functions.get(function_id)
    
    def get_function_by_name(self, name: str) -> Optional[FunctionInfo]:
        """
        Get a function by its name.
        
        Args:
            name: The name of the function to retrieve
            
        Returns:
            The FunctionInfo object if found, None otherwise
        """
        function_id = self.function_by_name.get(name)
        if function_id:
            return self.functions.get(function_id)
        return None
    
    def close(self):
        """Cleanup DDS entities"""
        if hasattr(self, 'execution_client'):
            self.execution_client.close()
        if hasattr(self, 'capability_reader'):
            self.capability_reader.close()
        if hasattr(self, 'capability_writer'):
            self.capability_writer.close()
        if hasattr(self, 'capability_topic'):
            self.capability_topic.close()
        if hasattr(self, 'subscriber'):
            self.subscriber.close()
        if hasattr(self, 'publisher'):
            self.publisher.close()
        
        # Clear references
        self.capability_writer = None
        self.capability_reader = None
        self.capability_topic = None
        self.subscriber = None
        self.publisher = None
        self.execution_client = None

class FunctionCapabilityListener(dds.DynamicData.NoOpDataReaderListener):
    """Listener for function capability advertisements"""
    def __init__(self, registry):
        super().__init__()
        self.registry = registry
        self.logger = configure_genesis_logging(
            logger_name=f"FunctionCapabilityListener.{id(registry)}",
            source_name=f"FuncCapListener-{id(registry)}",
            log_level=logging.INFO
        )
        self.processed_samples = set()  # Track processed sample IDs

    def on_subscription_matched(self, reader, info):
        """Handle subscription matches"""
        # First check if this is a FunctionCapability topic match
        if reader.topic_name != "FunctionCapability":
           # print(f"Ignoring subscription match for topic: {reader.topic_name}")
            return
            
        # Now we know this is a FunctionCapability topic match
        remote_guid = str(info.last_publication_handle)
        
        # Check if capability_writer exists before accessing it
        if hasattr(self.registry, 'capability_writer') and self.registry.capability_writer is not None:
            self_guid = str(self.registry.capability_writer.instance_handle) or "0"
        else:
            self_guid = "0"  # Default value if capability_writer is not available
            
        #print(f"FunctionCapability subscription matched with remote GUID: {remote_guid}")
        #print(f"FunctionCapability subscription matched with self GUID:   {self_guid}")
        
   

    def on_data_available(self, reader):
        """Handle new function capability advertisements"""
        try:
           # print("*********ODA******** Reader structure and methods:")
           # print(dir(reader))
            reader_matched_publications = reader.matched_publications
            #print("**********ODA******** Reader matched publications:")
            #print(dir(reader_matched_publications))
            current_publication = reader_matched_publications[0]
            #print(f"*********ODA********* Current publication: {current_publication}")
            samples = reader.take()
            for data, info in samples:
                # Create unique sample ID from function_id and timestamp
                sample_id = f"{data['function_id']}_{info.source_timestamp}"
                
                # Skip if we've already processed this sample
                if sample_id in self.processed_samples:
                    continue
                    
                if data and info.state.instance_state == dds.InstanceState.ALIVE:
                    self.registry.handle_capability_advertisement(data, info)
                    self.processed_samples.add(sample_id)
                   # print(f"DEBUG: FunctionCapabilityListener.on_data_available processed sample {sample_id}")
                    
                    # Clean up old samples (keep last 1000)
                    if len(self.processed_samples) > 1000:
                        self.processed_samples = set(list(self.processed_samples)[-1000:])
                        
        except Exception as e:
            self.logger.error(f"Error processing function capability: {e}")
    
    def on_liveliness_changed(self, reader, status):
        """Handle liveliness changes"""
        if status.not_alive_count > 0:
            self.registry.handle_capability_removal(reader)