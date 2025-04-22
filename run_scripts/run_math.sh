#!/bin/bash

# Get the absolute path of the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source the setup script from the project root
source "$PROJECT_ROOT/setup.sh"

# Add the project root to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT

# Start the calculator service in the background
echo "Starting calculator service..."
python "$PROJECT_ROOT/test_functions/calculator_service.py" > /dev/null 2>&1 &
SERVICE_PID=$!

# Wait for the service to start
echo "Waiting for service to start..."
sleep 3

# Run a simple test client
echo "Running test client..."
python -c "
import sys
import time
import asyncio
from genesis_lib.rpc_client import GenesisRPCClient

async def test_client():
    # Create a client
    client = GenesisRPCClient('CalculatorService')

    # Wait for service to be available
    time.sleep(1)

    # Test the add function
    result = await client.call_function('add', x=5, y=3)
    print(f'5 + 3 = {result}')

    # Test the multiply function
    result = await client.call_function('multiply', x=4, y=6)
    print(f'4 * 6 = {result}')

    print('Tests completed successfully')

# Run the async test
asyncio.run(test_client())
"

# Kill the service
echo "Stopping calculator service..."
kill $SERVICE_PID 2>/dev/null || true

echo "Test completed." 

