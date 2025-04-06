from dataclasses import field
from typing import Union, Sequence, Optional, Dict, Any
import rti.idl as idl
from enum import IntEnum
import sys
import os
import json

@idl.struct(
    member_annotations = {
        'name': [idl.bound(255)],
        'description': [idl.bound(255)],
    }
)
class Function:
    """
    OpenAI-style function definition with name, description, and parameters.
    """
    name: str = ""  # Name of the function
    description: str = ""  # Description of what the function does
    parameters: str = ""  # JSON-encoded parameters schema
    strict: bool = True  # Whether to enforce strict type checking

@idl.struct(
    member_annotations = {
        'type': [idl.bound(255)],
    }
)
class Tool:
    """
    OpenAI-style tool definition, currently only supporting function tools.
    """
    type: str = "function"  # Type of tool (currently only "function" is supported)
    function: Function = field(default_factory=Function)  # Function definition

@idl.struct(
    member_annotations = {
        'name': [idl.bound(255)],
        'arguments': [idl.bound(255)],
    }
)
class FunctionCall:
    """
    OpenAI-style function call with name and arguments.
    """
    name: str = ""  # Name of the function to call
    arguments: str = ""  # JSON-encoded arguments for the function

@idl.struct(
    member_annotations = {
        'id': [idl.bound(255)],
        'type': [idl.bound(255)],
    }
)
class FunctionRequest:
    """
    OpenAI-style function request with unique ID and type.
    """
    id: str = ""  # Unique identifier for the function call
    type: str = "function"  # Always "function" to match OpenAI format
    function: FunctionCall = field(default_factory=FunctionCall)  # Nested function call details

@idl.struct(
    member_annotations = {
        'result_json': [],  # No bound annotation means unbounded
        'error_message': [idl.bound(255)],
    }
)
class FunctionReply:
    """
    Reply from a function execution with result and status.
    """
    result_json: str = ""  # JSON-encoded result from the function
    success: bool = False  # Whether the function executed successfully
    error_message: str = ""  # Error message if the function failed

def validate_schema(schema: Dict[str, Any]) -> bool:
    """
    Validate that a schema follows OpenAI's function schema format.
    
    Args:
        schema: The schema to validate
        
    Returns:
        bool: True if valid, False otherwise
        
    Raises:
        ValueError: If the schema is invalid with details about why
    """
    required_fields = {"type", "properties"}
    if not isinstance(schema, dict):
        raise ValueError("Schema must be a dictionary")
    
    if not all(field in schema for field in required_fields):
        raise ValueError(f"Schema missing required fields: {required_fields - schema.keys()}")
    
    if schema["type"] != "object":
        raise ValueError('Schema "type" must be "object"')
    
    if not isinstance(schema["properties"], dict):
        raise ValueError("Schema properties must be a dictionary")
    
    for prop_name, prop in schema["properties"].items():
        if not isinstance(prop, dict):
            raise ValueError(f"Property {prop_name} must be a dictionary")
        if "type" not in prop:
            raise ValueError(f"Property {prop_name} missing required field 'type'")
        if "description" not in prop:
            raise ValueError(f"Property {prop_name} missing required field 'description'")
    
    return True 