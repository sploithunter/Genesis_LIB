#!/bin/bash

# Source the setup script from the project root
source ../setup.sh

# Add the project root to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(dirname $(dirname $(realpath $0)))

# Start the calculator service in the background
echo "Starting calculator service..."
python ../test_functions/calculator_service.py > /dev/null 2>&1 &
SERVICE_PID=$!

# Wait for the service to start
echo "Waiting for service to start..."
sleep 3

# Run a simple test client
echo "Running test client..."
python -c "
import sys
import time
from genesis_lib.rpc_client import RPCClient

# Create a client
client = RPCClient('CalculatorService')

# Wait for service to be available
time.sleep(1)

# Test the add function
result = client.call_function('add', {'a': 5, 'b': 3})
print(f'5 + 3 = {result}')

# Test the multiply function
result = client.call_function('multiply', {'a': 4, 'b': 6})
print(f'4 * 6 = {result}')

print('Tests completed successfully')
"

# Kill the service
echo "Stopping calculator service..."
kill $SERVICE_PID

echo "Test completed." 

