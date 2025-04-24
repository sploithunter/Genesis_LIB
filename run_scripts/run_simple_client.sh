#!/bin/bash

# Simple script to run the SimpleAgent with the SimpleClient
# This script starts the necessary function services, the SimpleAgent, and the SimpleClient

# Source the setup script to set up the environment
source ../setup.sh

# Add the project root to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(dirname $(dirname $(realpath $0)))

# Initialize array to store PIDs
declare -a pids=()

# Function to cleanup processes
cleanup() {
    echo "Cleaning up processes..."
    for pid in "${pids[@]}"; do
        if ps -p "$pid" > /dev/null; then
            kill "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null || true
        fi
    done
}

# Set up trap for cleanup on script termination
trap cleanup SIGINT SIGTERM EXIT

# Start the calculator service in the background
echo "Starting calculator service..."
python -m test_functions.calculator_service > /dev/null 2>&1 &
CALC_PID=$!
pids+=("$CALC_PID")

# Start the text processor service in the background
echo "Starting text processor service..."
python -m test_functions.text_processor_service > /dev/null 2>&1 &
TEXT_PID=$!
pids+=("$TEXT_PID")

# Start the letter counter service in the background
echo "Starting letter counter service..."
python -m test_functions.letter_counter_service > /dev/null 2>&1 &
LETTER_PID=$!
pids+=("$LETTER_PID")

# Wait for services to start
echo "Waiting for services to start..."
sleep 10

# Start the SimpleAgent
echo "Starting SimpleAgent..."
python ../genesis_lib/simple_agent.py > /dev/null 2>&1 &
AGENT_PID=$!
pids+=("$AGENT_PID")

# Wait for agent to start
sleep 10

# Run a test client that makes requests to the services
echo "Running test client..."
python -c "
import sys
import time
import asyncio
from genesis_lib.rpc_client import GenesisRPCClient

async def test_client():
    try:
        # Test calculator service
        calc_client = GenesisRPCClient('CalculatorService')
        print('Waiting for calculator service to be available...')
        await calc_client.wait_for_service(timeout_seconds=10)
        result = await calc_client.call_function('add', x=10, y=20)
        result_value = result.get('result')
        if result_value != 30:
            raise ValueError(f'Calculator test failed: expected 30, got {result_value}')
        print(f'Calculator test passed: 10 + 20 = {result_value}')

        # Test text processor service
        text_client = GenesisRPCClient('TextProcessorService')
        print('Waiting for text processor service to be available...')
        await text_client.wait_for_service(timeout_seconds=10)
        result = await text_client.call_function('count_words', text='This is a test sentence with seven words.')
        result_value = result.get('word_count')
        if result_value != 8:
            raise ValueError(f'Text processor test failed: expected 8, got {result_value}')
        print(f'Text processor test passed: Word count = {result_value}')

        # Test letter counter service
        letter_client = GenesisRPCClient('LetterCounterService')
        print('Waiting for letter counter service to be available...')
        await letter_client.wait_for_service(timeout_seconds=10)
        result = await letter_client.call_function('count_letter', text='Hello World', letter='l')
        result_value = result.get('result')
        if result_value != 3:
            raise ValueError(f'Letter counter test failed: expected 3, got {result_value}')
        print(f'Letter counter test passed: Letter count = {result_value}')

        print('All service tests completed successfully')
        return True
    except Exception as e:
        print(f'Error during test: {str(e)}', file=sys.stderr)
        return False

# Run the async test
success = asyncio.run(test_client())
sys.exit(0 if success else 1)
"
EXIT_CODE=$?

# Cleanup
cleanup

# Exit with test status
exit $EXIT_CODE 