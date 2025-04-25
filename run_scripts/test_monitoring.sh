#!/bin/bash

# test_monitoring.sh - A script to test monitoring functionality
# This script starts the monitoring test and example agent with functions

# Set strict error handling
set -e

# Configuration
TIMEOUT=60  # Timeout in seconds
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$SCRIPT_DIR/../logs"
DEBUG=${DEBUG:-false}  # Set to true to show debug output
mkdir -p "$LOG_DIR"

# Get the project root directory
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
[ "$DEBUG" = "true" ] && echo "Project root: $PROJECT_ROOT"

# Change to run_scripts directory
cd "$SCRIPT_DIR"
[ "$DEBUG" = "true" ] && echo "Changed to directory: $(pwd)"

# Initialize array to store PIDs
declare -a pids=()

# Function to display log content on failure
display_log_on_failure() {
    local log_file=$1
    local error_type=$2
    local error_message=$3
    
    echo "❌ ERROR: $error_message"
    echo "=================================================="
    echo "Log file contents ($log_file):"
    echo "=================================================="
    tail -n 20 "$log_file" | sed 's/^/  /'
    echo "=================================================="
    echo "Full log available at: $log_file"
    echo "=================================================="
}

# Function to cleanup processes
cleanup() {
    [ "$DEBUG" = "true" ] && echo "Cleaning up processes..."
    for pid in "${pids[@]}"; do
        if ps -p "$pid" > /dev/null; then
            kill "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null || true
        fi
    done
    pkill -f "python.*test_monitoring" || true
    pkill -f "python.*example_agent1" || true
}

# Set up trap for cleanup on script termination
trap cleanup EXIT

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: OPENAI_API_KEY environment variable is not set"
    echo "Please set your OpenAI API key before running this test"
    exit 1
fi

# Main execution
echo "Starting monitoring test..."
[ "$DEBUG" = "true" ] && echo "Logs will be saved to $LOG_DIR"

# Start multiple calculator services in the background
echo "Starting calculator services..."
for i in {1..3}; do
    PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT python -m test_functions.calculator_service > "$LOG_DIR/calculator_service_$i.log" 2>&1 &
    CALC_PID=$!
    pids+=("$CALC_PID")
    echo "Started calculator service $i with PID $CALC_PID"
done

# Wait for services to start
echo "Waiting for services to start..."
sleep 10

# Start the monitoring test in the background
echo "Starting monitoring test..."
PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT python test_monitoring.py > "$LOG_DIR/test_monitoring.log" 2>&1 &
MONITOR_PID=$!
pids+=("$MONITOR_PID")
echo "Started monitoring test with PID $MONITOR_PID"

# Wait a moment for the monitor to start
sleep 2

# Start example agent 1 with functions
echo "Starting test agent with functions..."
PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT python "$SCRIPT_DIR/test_agent.py" "Can you add 424242 and 111111?" > "$LOG_DIR/test_agent.log" 2>&1 &
AGENT_PID=$!
pids+=("$AGENT_PID")
echo "Started test agent with PID $AGENT_PID"

# Wait for the monitoring test to complete
echo "Waiting for monitoring test to complete..."
wait $MONITOR_PID
EXIT_CODE=$?

# Check the exit code
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Monitoring test completed successfully!"
else
    echo "❌ Monitoring test failed with exit code $EXIT_CODE"
    display_log_on_failure "$LOG_DIR/test_monitoring.log" "test_failure" "Monitoring test failed"
    exit 1
fi

# Exit with success
exit 0 