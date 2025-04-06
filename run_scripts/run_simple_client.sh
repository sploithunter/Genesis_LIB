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
from genesis_lib.rpc_client import RPCClient

# Test calculator service
calc_client = RPCClient('CalculatorService')
result = calc_client.call_function('add', {'a': 10, 'b': 20})
print(f'Calculator test: 10 + 20 = {result}')

# Test text processor service
text_client = RPCClient('TextProcessorService')
result = text_client.call_function('count_words', {'text': 'This is a test sentence with seven words.'})
print(f'Text processor test: Word count = {result}')

# Test letter counter service
letter_client = RPCClient('LetterCounterService')
result = letter_client.call_function('count_letters', {'text': 'Hello World'})
print(f'Letter counter test: Letter count = {result}')

print('All service tests completed successfully')
"

# Clean up
echo "Stopping agent and services..."
kill $AGENT_PID $CALC_PID $TEXT_PID $LETTER_PID

echo "Done." 