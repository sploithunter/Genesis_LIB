#!/usr/bin/env python3
"""
Lightweight decorator to declare & register GENESIS functions in one step.
"""

from __future__ import annotations
import json, inspect, typing
from typing import Any, Callable, Dict, Optional, Type

__all__ = ["genesis_function", "infer_schema_from_annotations", "validate_args"]

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def infer_schema_from_annotations(fn: Callable) -> Dict[str, Any]:
    """Draft‑07 JSON‑Schema synthesised from type annotations."""
    sig   = inspect.signature(fn)
    hints = typing.get_type_hints(fn)

    props, required = {}, []
    for name, param in sig.parameters.items():
        if name in ("self", "request_info"):
            continue
        typ = hints.get(name, Any)
        schema = {"description": "", "type": _python_type_to_json(typ)}
        props[name] = schema
        if param.default is inspect._empty:
            required.append(name)

    return {"type": "object", "properties": props, "required": required}

def _python_type_to_json(t) -> str:
    return {int: "integer", float: "number", str: "string", bool: "boolean"}.get(t, "string")

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
    """
    def decorator(fn: Callable):
        # Build / derive schema
        if model is not None:
            schema = json.loads(model.schema_json())
        elif parameters is not None:
            schema = parameters
        else:
            schema = infer_schema_from_annotations(fn)

        fn.__genesis_meta__ = {
            "description": description or (fn.__doc__ or ""),
            "parameters":  schema,
            "operation_type": operation_type,
            "common_patterns": common_patterns,
            "pydantic_model": model,
        }
        return fn
    return decorator
