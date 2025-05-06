from __future__ import annotations

#!/usr/bin/env python3

"""
Genesis Function Decorator System

This module provides a powerful decorator system for automatically generating and managing
function schemas within the Genesis framework. It enables seamless integration between
Python functions and large language models by automatically inferring and validating
function signatures, parameters, and documentation.

Key features:
- Automatic schema generation from Python type hints and docstrings
- Support for complex type annotations (Unions, Lists, Dicts)
- Parameter validation and coercion using Pydantic models
- OpenAI-compatible function schema generation
- Intelligent parameter description extraction from docstrings

The @genesis_function decorator allows developers to expose their functions to LLMs
without manually writing JSON schemas, making the Genesis network more accessible
and maintainable.

Example:
    @genesis_function
    def calculate_sum(a: int, b: int) -> int:
        \"\"\"Add two numbers together.
        
        Args:
            a: First number to add
            b: Second number to add
        \"\"\"
        return a + b

Copyright (c) 2025, RTI & Jason Upchurch
"""

import json, inspect, typing, re
from typing import Any, Callable, Dict, Optional, Type, Union, get_origin, get_args

__all__ = ["genesis_function", "infer_schema_from_annotations", "validate_args"]

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _extract_param_descriptions(docstring: Optional[str]) -> Dict[str, str]:
    """Extract parameter descriptions from docstring Args section."""
    if not docstring:
        return {}
    
    # Find the Args section
    args_match = re.search(r'Args:\s*\n(.*?)(?=\n\s*\n|\Z)', docstring, re.DOTALL)
    if not args_match:
        return {}
    
    args_section = args_match.group(1)
    descriptions = {}
    
    # Parse each parameter line
    for line in args_section.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Match parameter name and description
        param_match = re.match(r'(\w+):\s*(.*)', line)
        if param_match:
            param_name, description = param_match.groups()
            descriptions[param_name] = description.strip()
    
    return descriptions

def _python_type_to_json(t) -> Union[str, Dict[str, Any]]:
    """Convert Python type to JSON schema type with support for complex types."""
    # Handle Union types (including Optional)
    if get_origin(t) is Union:
        types = [arg for arg in get_args(t) if arg is not type(None)]
        if len(types) == 1:
            return _python_type_to_json(types[0])
        return {"oneOf": [_python_type_to_json(arg) for arg in types]}
    
    # Handle List/Sequence types
    if get_origin(t) in (list, typing.List, typing.Sequence):
        item_type = get_args(t)[0]
        return {"type": "array", "items": _python_type_to_json(item_type)}
    
    # Handle Dict types
    if get_origin(t) in (dict, typing.Dict):
        key_type, value_type = get_args(t)
        if key_type is str:  # Only support string keys for now
            return {
                "type": "object",
                "additionalProperties": _python_type_to_json(value_type)
            }
        return "object"  # Fallback for non-string keys
    
    # Basic types
    type_map = {
        int: "integer",
        float: "number",
        str: "string",
        bool: "boolean",
        type(None): "null",
        Dict: "object",
        dict: "object",
        Any: "object"
    }
    
    return type_map.get(t, "string")

def infer_schema_from_annotations(fn: Callable) -> Dict[str, Any]:
    """Draft‑07 JSON‑Schema synthesised from type annotations and docstring."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)
    descriptions = _extract_param_descriptions(fn.__doc__)

    props = {}
    required = []
    
    for name, param in sig.parameters.items():
        if name in ("self", "request_info"):
            continue
            
        typ = hints.get(name, Any)
        type_info = _python_type_to_json(typ)
        
        # Create schema with type and description
        if isinstance(type_info, str):
            schema = {
                "type": type_info,
                "description": descriptions.get(name, "")
            }
        else:
            schema = {
                **type_info,  # This includes type and any additional info
                "description": descriptions.get(name, "")
            }
        
        # Add example if available in docstring
        if name in descriptions and "example" in descriptions[name].lower():
            example_match = re.search(r'example:\s*([^\n]+)', descriptions[name], re.IGNORECASE)
            if example_match:
                try:
                    schema["example"] = eval(example_match.group(1))
                except:
                    pass
        
        props[name] = schema
        if param.default is inspect._empty:
            required.append(name)

    # Create the full schema in the format expected by the function registry
    schema = {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False  # Prevent additional properties
    }
    
    # Convert to JSON string and back to ensure it's serializable
    return json.loads(json.dumps(schema))

def validate_args(fn: Callable, kwargs: Dict[str, Any]) -> None:
    """If a Pydantic model was supplied, validate/coerce kwargs in‑place."""
    model = getattr(fn, "__genesis_meta__", {}).get("pydantic_model")
    if model:
        obj = model(**{k: v for k, v in kwargs.items() if k != "request_info"})
        kwargs.update(obj.model_dump())

# --------------------------------------------------------------------------- #
# Decorator                                                                   #
# --------------------------------------------------------------------------- #
def genesis_function(
    *,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    model: Optional[Type] = None,
    operation_type: Optional[str] = None,
    common_patterns: Optional[Dict[str, Any]] = None,
):
    """
    Attach JSON‑schema & metadata to a function so EnhancedServiceBase can
    auto‑register it.
    
    The schema can be provided in three ways:
    1. Explicitly via the parameters argument
    2. Via a Pydantic model using the model argument
    3. Implicitly inferred from type hints and docstring (default)
    """
    def decorator(fn: Callable):
        # Build / derive schema
        if model is not None:
            schema = json.loads(model.schema_json())
        elif parameters is not None:
            schema = parameters
        else:
            schema = infer_schema_from_annotations(fn)

        # Ensure schema is serialized as JSON string
        schema_str = json.dumps(schema)

        fn.__genesis_meta__ = {
            "description": description or (fn.__doc__ or ""),
            "parameters": schema_str,  # Store as JSON string
            "operation_type": operation_type,
            "common_patterns": common_patterns,
            "pydantic_model": model,
        }
        return fn
    return decorator
