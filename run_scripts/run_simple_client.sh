#!/bin/bash

# Simple script to run the SimpleAgent with the SimpleClient
# This script starts the necessary function services, the SimpleAgent, and the SimpleClient

# Source the setup script to set up the environment
source ../setup.sh

# Add the project root to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(dirname $(dirname $(realpath $0)))

# Start the calculator service in the background
echo "Starting calculator service..."
python -m test_functions.calculator_service > /dev/null 2>&1 &
CALC_PID=$!

# Start the text processor service in the background
echo "Starting text processor service..."
python -m test_functions.text_processor_service > /dev/null 2>&1 &
TEXT_PID=$!

# Start the letter counter service in the background
echo "Starting letter counter service..."
python -m test_functions.letter_counter_service > /dev/null 2>&1 &
LETTER_PID=$!

# Wait for services to start
echo "Waiting for services to start..."
sleep 3

# Start the SimpleAgent
echo "Starting SimpleAgent..."
python ../genesis_lib/simple_agent.py > /dev/null 2>&1 &
AGENT_PID=$!

# Wait for agent to start
sleep 2

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
        print(f'Calculator test: 10 + 20 = {result}')

        # Test text processor service
        text_client = GenesisRPCClient('TextProcessorService')
        print('Waiting for text processor service to be available...')
        await text_client.wait_for_service(timeout_seconds=10)
        result = await text_client.call_function('count_words', text='This is a test sentence with seven words.')
        print(f'Text processor test: Word count = {result}')

        # Test letter counter service
        letter_client = GenesisRPCClient('LetterCounterService')
        print('Waiting for letter counter service to be available...')
        await letter_client.wait_for_service(timeout_seconds=10)
        result = await letter_client.call_function('count_letter', text='Hello World', letter='l')
        print(f'Letter counter test: Letter count = {result}')

        print('All service tests completed successfully')
    except Exception as e:
        print(f'Error during test: {str(e)}')
        sys.exit(1)

# Run the async test
asyncio.run(test_client())
"

# Clean up
echo "Stopping agent and services..."
kill $AGENT_PID $CALC_PID $TEXT_PID $LETTER_PID 2>/dev/null || true

echo "Done." 