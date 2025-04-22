#!/bin/bash

# run_all_tests.sh - A script to run all Genesis-LIB test scripts with timeouts
# This script runs each test script with a timeout and proper error handling
# If any test fails, the script will stop for debugging

# Set strict error handling
set -e

# Configuration
TIMEOUT=120  # Default timeout in seconds
LOG_DIR="../logs"
mkdir -p "$LOG_DIR"

# Get the project root directory
PROJECT_ROOT=$(dirname $(dirname $(realpath $0)))
echo "Project root: $PROJECT_ROOT"

# Function to run a script with timeout and log output
run_with_timeout() {
    local script_name=$1
    local timeout=$2
    local log_file="$LOG_DIR/${script_name%.*}.log"
    
    echo "=================================================="
    echo "Running $script_name with ${timeout}s timeout..."
    echo "Log file: $log_file"
    echo "=================================================="
    
    # Determine if this is a Python script or a shell script
    if [[ "$script_name" == *.py ]]; then
        # Run Python script with timeout and capture output
        PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT timeout $timeout python "$script_name" > "$log_file" 2>&1
    else
        # Run shell script with timeout and capture output
        PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT timeout $timeout bash "$script_name" > "$log_file" 2>&1
    fi
    
    # Check exit status
    local exit_code=$?
    if [ $exit_code -eq 124 ]; then
        echo "❌ ERROR: $script_name timed out after ${timeout}s"
        # Clean up any processes that might still be running
        cleanup
        return 1
    elif [ $exit_code -ne 0 ]; then
        echo "❌ ERROR: $script_name failed with exit code $exit_code"
        echo "Check $log_file for details"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for test failures in the log
    if grep -q "Some tests failed" "$log_file"; then
        echo "❌ ERROR: $script_name reported test failures"
        echo "Check $log_file for details"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for Python errors in the log
    if grep -q "ImportError\|NameError\|TypeError\|AttributeError\|RuntimeError\|SyntaxError\|IndentationError" "$log_file"; then
        echo "❌ ERROR: $script_name encountered Python errors"
        echo "Check $log_file for details"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for any error messages in the log
    if grep -q "ERROR\|Error\|error\|Exception\|exception\|Traceback" "$log_file"; then
        echo "❌ ERROR: $script_name encountered errors"
        echo "Check $log_file for details"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for unexpected termination
    if grep -q "Killed\|Segmentation fault\|Aborted\|core dumped" "$log_file"; then
        echo "❌ ERROR: $script_name terminated unexpectedly"
        echo "Check $log_file for details"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    echo "✅ SUCCESS: $script_name completed successfully"
    return 0
}

# Function to clean up processes
cleanup() {
    echo "Cleaning up any remaining processes..."
    pkill -f "python.*calculator_service" || true
    pkill -f "python.*text_processor_service" || true
    pkill -f "python.*letter_counter_service" || true
    pkill -f "python.*simple_agent" || true
    pkill -f "python.*simple_client" || true
    pkill -f "python.*openai_chat_agent" || true
    pkill -f "python.*interface_cli" || true
    echo "Cleanup complete"
}

# Set up trap for cleanup on script termination
trap cleanup EXIT

# Main execution
echo "Starting Genesis-LIB test suite..."
echo "Logs will be saved to $LOG_DIR"

# Run each test script with appropriate timeout
# Basic calculator test
run_with_timeout "run_math.sh" 30 || { echo "Test failed: run_math.sh"; exit 1; }

# Multi-instance calculator test
run_with_timeout "run_multi_math.sh" 60 || { echo "Test failed: run_multi_math.sh"; exit 1; }

# Simple agent test
run_with_timeout "run_simple_agent.sh" 60 || { echo "Test failed: run_simple_agent.sh"; exit 1; }

# Simple client test
run_with_timeout "run_simple_client.sh" 60 || { echo "Test failed: run_simple_client.sh"; exit 1; }

# Services and agent test
run_with_timeout "start_services_and_agent.py" 90 || { echo "Test failed: start_services_and_agent.py"; exit 1; }

# Services and CLI test
run_with_timeout "start_services_and_cli.sh" 90 || { echo "Test failed: start_services_and_cli.sh"; exit 1; }

# Genesis framework test
run_with_timeout "test_genesis_framework.sh" 120 || { echo "Test failed: test_genesis_framework.sh"; exit 1; }

echo "=================================================="
echo "All tests completed successfully!"
echo "Logs are available in $LOG_DIR"
echo "==================================================" 