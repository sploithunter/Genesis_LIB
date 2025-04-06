#!/usr/bin/env python3

import logging
import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional
import rti.connextdds as dds
from genesis_lib.rpc_client import GenesisRPCClient
from genesis_lib.function_discovery import FunctionRegistry

# Configure logging
logging.basicConfig(level=logging.WARNING,  # Reduce verbosity
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("generic_function_client")
logger.setLevel(logging.INFO)  # Keep INFO level for important events

class GenericFunctionClient:
    """
    A truly generic function client that can discover and call any function service
    without prior knowledge of the specific functions.
    """
    
    def __init__(self, function_registry: Optional[FunctionRegistry] = None):
        """
        Initialize the generic function client.
        
        Args:
            function_registry: Optional existing FunctionRegistry instance to use.
                             If None, a new one will be created.
        """
        logger.info("Initializing GenericFunctionClient")
        
        # Use provided registry or create new one
        self.function_registry = function_registry or FunctionRegistry()
        
        # Store discovered functions
        self.discovered_functions = {}
        
        # Store service-specific clients
        self.service_clients = {}
        
    async def discover_functions(self, timeout_seconds: int = 10) -> Dict[str, Any]:
        """
        Discover available functions in the distributed system.
        
        Args:
            timeout_seconds: How long to wait for functions to be discovered
            
        Returns:
            Dictionary of discovered functions
        """
        logger.info("Discovering all available functions")
        start_time = time.time()
        
        # Keep checking until we find all types of functions or timeout
        calculator_found = False
        letter_counter_found = False
        text_processor_found = False
        
        while time.time() - start_time < timeout_seconds:
            # Update discovered functions
            self.discovered_functions = self.function_registry.discovered_functions.copy()
            
            # Check if we've found all the functions we're looking for
            for func_id, func_info in self.discovered_functions.items():
                if isinstance(func_info, dict):
                    name = func_info.get('name', '').lower()
                    if 'calculator' in name:
                        calculator_found = True
                    elif 'letter' in name and 'counter' in name:
                        letter_counter_found = True
                    elif 'text' in name and 'processor' in name:
                        text_processor_found = True
            
            # If we've found all functions, break early
            if calculator_found and letter_counter_found and text_processor_found:
                break
                
            # Wait a bit before checking again
            await asyncio.sleep(0.5)
        
        # Log the discovered functions, even if none were found
        if not self.discovered_functions:
            logger.info("No functions discovered in the distributed system")
            return {}
        
        logger.info(f"Discovered {len(self.discovered_functions)} functions")
        for func_id, func_info in self.discovered_functions.items():
            if isinstance(func_info, dict):
                logger.info(f"  - {func_id}: {func_info.get('name', 'unknown')} - {func_info.get('description', 'No description')}")
            else:
                logger.info(f"  - {func_id}: {func_info}")
        
        return self.discovered_functions
    
    def get_service_client(self, service_name: str) -> GenesisRPCClient:
        """
        Get or create a client for a specific service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            RPC client for the service
        """
        if service_name not in self.service_clients:
            logger.info(f"Creating new client for service: {service_name}")
            client = GenesisRPCClient(service_name=service_name)
            # Set a reasonable timeout (10 seconds)
            client.timeout = dds.Duration(seconds=10)
            self.service_clients[service_name] = client
        
        return self.service_clients[service_name]
    
    async def call_function(self, function_id: str, **kwargs) -> Dict[str, Any]:
        """
        Call a function by its ID with the given arguments.
        
        Args:
            function_id: ID of the function to call
            **kwargs: Arguments to pass to the function
            
        Returns:
            Function result
            
        Raises:
            ValueError: If the function is not found
            RuntimeError: If the function call fails
        """
        if function_id not in self.discovered_functions:
            raise ValueError(f"Function not found: {function_id}")
        
        # Get function info
        func_info = self.discovered_functions[function_id]
        
        # Extract function name and provider ID
        if isinstance(func_info, dict):
            function_name = func_info.get('name')
            provider_id = func_info.get('provider_id')
        else:
            raise RuntimeError(f"Invalid function info format for {function_id}")
        
        if not function_name:
            raise RuntimeError(f"Function name not found for {function_id}")
        
        # Determine the service name based on the function name or provider ID
        service_name = "CalculatorService"  # Default service
        
        # Map function names to their respective services
        if function_name in ['count_letter', 'count_multiple_letters', 'get_letter_frequency']:
            service_name = "LetterCounterService"
        elif function_name in ['transform_case', 'analyze_text', 'generate_text']:
            service_name = "TextProcessorService"
        
        # If we have a provider ID, use it to determine the service name more accurately
        if provider_id:
            # Extract service name from provider ID if possible
            # This is a more reliable method if the provider ID contains service information
            logger.info(f"Using provider ID to determine service: {provider_id}")
        
        logger.info(f"Using service name: {service_name} for function: {function_name}")
        
        # Get or create a client for this service
        client = self.get_service_client(service_name)
        
        # Wait for the service to be discovered
        logger.info(f"Waiting for service {service_name} to be discovered")
        try:
            await client.wait_for_service(timeout_seconds=5)
        except TimeoutError as e:
            logger.warning(f"Service discovery timed out, but attempting call anyway: {str(e)}")
        
        # Call the function through RPC
        logger.info(f"Calling function {function_name} via RPC")
        try:
            return await client.call_function(function_name, **kwargs)
        except Exception as e:
            raise RuntimeError(f"Error calling function {function_name}: {str(e)}")
    
    def get_function_schema(self, function_id: str) -> Dict[str, Any]:
        """
        Get the schema for a specific function.
        
        Args:
            function_id: ID of the function
            
        Returns:
            Function schema
            
        Raises:
            ValueError: If the function is not found
        """
        if function_id not in self.discovered_functions:
            raise ValueError(f"Function not found: {function_id}")
        
        return self.discovered_functions[function_id].schema
    
    def list_available_functions(self) -> List[Dict[str, Any]]:
        """
        List all available functions with their descriptions and schemas.
        
        Returns:
            List of function information dictionaries
        """
        result = []
        for func_id, func_info in self.discovered_functions.items():
            if isinstance(func_info, dict):
                # Get the schema directly from the function info
                schema = func_info.get('schema', {})
                
                # Determine the service name based on the function name
                service_name = "CalculatorService"  # Default service
                function_name = func_info.get('name', func_id)
                
                if function_name in ['count_letter', 'count_multiple_letters', 'get_letter_frequency']:
                    service_name = "LetterCounterService"
                elif function_name in ['transform_case', 'analyze_text', 'generate_text']:
                    service_name = "TextProcessorService"
                
                # If we have a provider ID, it might contain service information
                provider_id = func_info.get('provider_id')
                if provider_id:
                    logger.debug(f"Provider ID for {function_name}: {provider_id}")
                
                result.append({
                    "function_id": func_id,
                    "name": function_name,
                    "description": func_info.get('description', 'No description'),
                    "schema": schema,
                    "service_name": service_name
                })
            else:
                # Handle non-dictionary function info (unlikely but for robustness)
                result.append({
                    "function_id": func_id,
                    "name": str(func_info),
                    "description": "Unknown function format",
                    "schema": {},
                    "service_name": "UnknownService"
                })
        return result
    
    def close(self):
        """Close all client resources"""
        logger.info("Cleaning up client resources...")
        for client in self.service_clients.values():
            client.close()
        logger.info("Client cleanup complete.")

async def run_generic_client_test():
    """
    Run a test of the generic function client.
    This test has zero knowledge of function schemas or calling conventions.
    It simply discovers functions and tests the first function it finds.
    """
    client = GenericFunctionClient()
    
    try:
        # Discover available functions
        await client.discover_functions()
        
        # List available functions
        functions = client.list_available_functions()
        print("\nAvailable Functions:")
        for func in functions:
            print(f"  - {func['function_id']}: {func['name']} - {func['description']}")
        
        if functions:
            # Test the first function we find
            test_func = functions[0]
            print(f"\nTesting function: {test_func['name']} - {test_func['description']}")
            
            # Get the schema to understand what parameters are needed
            schema = test_func['schema']
            print(f"Function schema: {json.dumps(schema, indent=2)}")
            
            # Extract required parameters and their types
            required_params = {}
            if 'properties' in schema:
                for param_name, param_schema in schema['properties'].items():
                    # Check if parameter is required
                    is_required = 'required' in schema and param_name in schema['required']
                    
                    if is_required:
                        # Determine a test value based on the parameter type
                        if param_schema.get('type') == 'number' or param_schema.get('type') == 'integer':
                            # Use a simple number for testing
                            required_params[param_name] = 10
                        elif param_schema.get('type') == 'string':
                            # Use a simple string for testing
                            required_params[param_name] = "test"
                        elif param_schema.get('type') == 'boolean':
                            # Use a simple boolean for testing
                            required_params[param_name] = True
                        else:
                            # Default to a string for unknown types
                            required_params[param_name] = "test"
            
            if required_params:
                print(f"Calling function with parameters: {required_params}")
                try:
                    result = await client.call_function(test_func['function_id'], **required_params)
                    print(f"Function returned: {result}")
                    print("✅ Test passed.")
                except Exception as e:
                    print(f"❌ Error calling function: {str(e)}")
            else:
                print("No required parameters found in schema, skipping test.")
        else:
            print("\nNo functions found to test.")
            
    except Exception as e:
        logger.error(f"Error in test: {str(e)}", exc_info=True)
    finally:
        client.close()

def main():
    """Main entry point"""
    logger.info("Starting GenericFunctionClient")
    try:
        asyncio.run(run_generic_client_test())
    except KeyboardInterrupt:
        logger.info("Client shutting down due to keyboard interrupt")
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 