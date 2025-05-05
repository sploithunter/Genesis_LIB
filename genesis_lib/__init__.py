"""
GENESIS Library - A distributed function discovery and execution framework
"""

import logging
from .logging_config import configure_genesis_logging

# Configure root logger for genesis_lib
configure_genesis_logging("genesis_lib", "genesis_lib", logging.INFO)

from .genesis_app import GenesisApp
from .agent import GenesisAgent
from .interface import GenesisInterface
from .function_discovery import (
    FunctionRegistry,
    FunctionInfo
)
from .function_classifier import FunctionClassifier
from .llm import AnthropicChatAgent
from .openai_genesis_agent import OpenAIGenesisAgent
from .function_client import GenericFunctionClient
from .utils.openai_utils import convert_functions_to_openai_schema, generate_response_with_functions
from .utils.function_utils import call_function_thread_safe, find_function_by_name, filter_functions_by_relevance
from .utils import get_datamodel_path, load_datamodel

__all__ = [
    'GenesisApp',
    'GenesisAgent',
    'GenesisInterface',
    'FunctionRegistry',
    'FunctionInfo',
    'FunctionClassifier',
    'AnthropicChatAgent',
    'OpenAIGenesisAgent',
    'GenericFunctionClient',
    'convert_functions_to_openai_schema',
    'generate_response_with_functions',
    'call_function_thread_safe',
    'find_function_by_name',
    'filter_functions_by_relevance',
    'get_datamodel_path',
    'load_datamodel'
] 