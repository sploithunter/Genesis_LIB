#!/bin/bash

# run_all_tests.sh - A script to run all Genesis-LIB test scripts with timeouts
# This script runs each test script with a timeout and proper error handling
# If any test fails, the script will stop for debugging

# Set strict error handling
set -e

# Configuration
TIMEOUT=120  # Default timeout in seconds
DEBUG=${DEBUG:-false}  # Set to true to show debug output

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# If we're not in the run_scripts directory, cd to it
if [ "$(basename "$PWD")" != "run_scripts" ]; then
    cd "$SCRIPT_DIR"
fi

# Set up log directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

[ "$DEBUG" = "true" ] && echo "Project root: $PROJECT_ROOT"
[ "$DEBUG" = "true" ] && echo "Script directory: $SCRIPT_DIR"
[ "$DEBUG" = "true" ] && echo "Log directory: $LOG_DIR"

# Function to display log content on failure
display_log_on_failure() {
    local log_file=$1
    local error_type=$2
    local error_message=$3
    
    echo "❌ ERROR: $error_message"
    echo "=================================================="
    echo "Log file contents ($log_file):"
    echo "=================================================="
    # Show the last 20 lines of the log file, or the whole file if it's shorter
    tail -n 20 "$log_file" | sed 's/^/  /'
    echo "=================================================="
    echo "Full log available at: $log_file"
    echo "=================================================="
}

# Function to run a script with timeout and log output
run_with_timeout() {
    local script_name=$1
    local timeout=$2
    local script_basename=$(basename "$script_name")
    local log_file="$LOG_DIR/${script_basename%.*}.log"
    
    echo "=================================================="
    echo "Running $script_name with ${timeout}s timeout..."
    [ "$DEBUG" = "true" ] && echo "Log file: $log_file"
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
        display_log_on_failure "$log_file" "timeout" "$script_name timed out after ${timeout}s"
        # Clean up any processes that might still be running
        cleanup
        return 1
    elif [ $exit_code -ne 0 ]; then
        display_log_on_failure "$log_file" "exit_code" "$script_name failed with exit code $exit_code"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for test failures in the log
    if grep -q "Some tests failed" "$log_file"; then
        display_log_on_failure "$log_file" "test_failure" "$script_name reported test failures"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for Python errors in the log
    if grep -q "ImportError\|NameError\|TypeError\|AttributeError\|RuntimeError\|SyntaxError\|IndentationError" "$log_file"; then
        display_log_on_failure "$log_file" "python_error" "$script_name encountered Python errors"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    # Check for unexpected error messages in the log, excluding expected ones
    # Create a temporary file with filtered content
    local temp_log=$(mktemp)
    # Filter out INFO, DEBUG, and expected warning/error messages
    grep -v "INFO\|DEBUG\|WARNING\|Cannot divide by zero\|Function call failed\|All calculator tests completed successfully\|Debug: \|test passed\|Test passed\|DivisionByZeroError\|Error executing function: Cannot divide by zero" "$log_file" > "$temp_log"
    
    # Only show debug output if DEBUG is true
    if [ "$DEBUG" = "true" ]; then
        echo "Debug: Remaining content after filtering:"
        cat "$temp_log"
        echo "Debug: End of filtered content"
    fi
    
    # Check for remaining error messages, being more specific about what constitutes an error
    if grep -q "^ERROR:\|^Error:\|^error:" "$temp_log" || \
       (grep -q "Traceback (most recent call last)" "$temp_log" && \
        ! grep -q "DivisionByZeroError: Cannot divide by zero" "$log_file"); then
        display_log_on_failure "$log_file" "unexpected_error" "$script_name encountered unexpected errors"
        # Show the matching lines
        if [ "$DEBUG" = "true" ]; then
            echo "Debug: Lines containing errors:"
            grep "^ERROR:\|^Error:\|^error:\|Traceback (most recent call last)\|Exception:" "$temp_log"
            echo "Debug: End of error lines"
        fi
        rm "$temp_log"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    rm "$temp_log"
    
    # Check for unexpected termination
    if grep -q "Killed\|Segmentation fault\|Aborted\|core dumped" "$log_file"; then
        display_log_on_failure "$log_file" "termination" "$script_name terminated unexpectedly"
        # Clean up any processes that might still be running
        cleanup
        return 1
    fi
    
    echo "✅ SUCCESS: $script_name completed successfully"
    return 0
}

# Function to clean up processes
cleanup() {
    [ "$DEBUG" = "true" ] && echo "Cleaning up any remaining processes..."
    pkill -f "python.*calculator_service" || true
    pkill -f "python.*text_processor_service" || true
    pkill -f "python.*letter_counter_service" || true
    pkill -f "python.*simple_agent" || true
    pkill -f "python.*simple_client" || true
    pkill -f "python.*openai_chat_agent" || true
    pkill -f "python.*interface_cli" || true
    pkill -f "python.*test_agent" || true
    [ "$DEBUG" = "true" ] && echo "Cleanup complete"
}

# Set up trap for cleanup on script termination
trap cleanup EXIT

# Main execution
echo "Starting Genesis-LIB test suite..."
[ "$DEBUG" = "true" ] && echo "Logs will be saved to $LOG_DIR"

# Run each test script with appropriate timeout
# Basic calculator test
run_with_timeout "run_math.sh" 30 || { echo "Test failed: run_math.sh"; exit 1; }

# Multi-instance calculator test
run_with_timeout "run_multi_math.sh" 60 || { echo "Test failed: run_multi_math.sh"; exit 1; }

# Simple agent test
run_with_timeout "run_simple_agent.sh" 60 || { echo "Test failed: run_simple_agent.sh"; exit 1; }

# Simple client test
run_with_timeout "run_simple_client.sh" 60 || { echo "Test failed: run_simple_client.sh"; exit 1; }

# Example agent test
DEBUG=true run_with_timeout "run_test_agent_with_functions.sh" 60 || { echo "Test failed: run_test_agent_with_functions.sh"; exit 1; }

# Services and agent test
run_with_timeout "start_services_and_agent.py" 90 || { echo "Test failed: start_services_and_agent.py"; exit 1; }

# Services and CLI test
run_with_timeout "start_services_and_cli.sh" 90 || { echo "Test failed: start_services_and_cli.sh"; exit 1; }

# Genesis framework test
run_with_timeout "test_genesis_framework.sh" 120 || { echo "Test failed: test_genesis_framework.sh"; exit 1; }

# Monitoring test
run_with_timeout "test_monitoring.sh" 60 || { echo "Test failed: test_monitoring.sh"; exit 1; }

echo "=================================================="
echo "All tests completed successfully!"
[ "$DEBUG" = "true" ] && echo "Logs are available in $LOG_DIR"
echo "==================================================" 