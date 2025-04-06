#!/bin/bash

# Source the setup script to set environment variables
echo "===== Sourcing setup.sh ====="
source setup.sh

# Start the calculator service
echo "===== Starting Calculator Service ====="
source setup.sh && python3 test_functions/calculator_service.py &
CALCULATOR_PID=$!

# Start the letter counter service
echo "===== Starting Letter Counter Service ====="
source setup.sh && python3 test_functions/letter_counter_service.py &
LETTER_COUNTER_PID=$!

# Start the text processor service
echo "===== Starting Text Processor Service ====="
source setup.sh && python3 test_functions/text_processor_service.py &
TEXT_PROCESSOR_PID=$!

# Wait for services to initialize
echo "Waiting 5 seconds for services to initialize..."
sleep 5

# Start the CLI agent
#echo "===== Starting CLI Agent ====="
##source setup.sh && python3 test_agents/cli_direct_agent.py

# Clean up on exit
echo "===== Cleaning Up ====="
kill $CALCULATOR_PID 2>/dev/null || true
kill $LETTER_COUNTER_PID 2>/dev/null || true
kill $TEXT_PROCESSOR_PID 2>/dev/null || true

# Wait for processes to finish
wait $CALCULATOR_PID 2>/dev/null || true
wait $LETTER_COUNTER_PID 2>/dev/null || true
wait $TEXT_PROCESSOR_PID 2>/dev/null || true

echo "===== All done =====" 