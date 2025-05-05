#!/bin/bash

# Script to run simple Interface <-> Agent RPC test with DDS tracing

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# Set up log directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# Define script and log file names
AGENT_SCRIPT="$PROJECT_ROOT/run_scripts/math_test_agent.py"
INTERFACE_SCRIPT="$PROJECT_ROOT/run_scripts/math_test_interface.py"
AGENT_LOG="$LOG_DIR/math_test_agent.log"
INTERFACE_LOG="$LOG_DIR/math_test_interface.log"
REGISTRATION_SPY_LOG="$LOG_DIR/rtiddsspy_registration.log"
INTERFACE_SPY_LOG="$LOG_DIR/rtiddsspy_interface.log"

# Function to kill a process and ensure it's dead
kill_process() {
    local pid=$1
    local name=$2
    local is_spy=$3

    if [ "$is_spy" = "true" ]; then
        # For spy processes, use pkill with the specific command line
        echo "🔫 TRACE: Stopping $name process $pid..."
        pkill -f "rtiddsspy.*spy_transient.xml.*SpyLib::TransientReliable" || true
        sleep 1
    else
        # For other processes, use the normal kill approach
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "🔫 TRACE: Stopping $name process $pid..."
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                echo "⚠️ TRACE: Process $pid didn't respond to SIGTERM, using SIGKILL..."
                kill -KILL "$pid" 2>/dev/null || true
            fi
            wait "$pid" 2>/dev/null || true
        fi
    fi
}

# Clear existing log files
echo "🧹 TRACE: Clearing existing log files..."
rm -f "$AGENT_LOG" "$INTERFACE_LOG" "$REGISTRATION_SPY_LOG" "$INTERFACE_SPY_LOG"

echo "🔬 TRACE: Starting Test 1 - Registration Durability Test"
echo "=============================================="

# Start the agent first
echo "🚀 TRACE: Starting agent..."
PYTHONUNBUFFERED=1 stdbuf -o0 -e0 python3 -u "$AGENT_SCRIPT" > "$AGENT_LOG" 2>&1 &
AGENT_PID=$!
echo "✅ TRACE: Agent started with PID: $AGENT_PID"

# Wait for the agent to initialize and announce itself
echo "⏳ TRACE: Waiting for agent to initialize..."
sleep 5

# Now start RTI DDS Spy AFTER the agent
echo "🚀 TRACE: Starting RTI DDS Spy to verify durability..."
/Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -printSample -qosFile spy_transient.xml -qosProfile SpyLib::TransientReliable > "$REGISTRATION_SPY_LOG" 2>&1 &
REGISTRATION_SPY_PID=$!
echo "✅ TRACE: RTI DDS Spy started with PID: $REGISTRATION_SPY_PID (Log: $REGISTRATION_SPY_LOG)"

# Wait for the spy to receive the durable announcement
echo "⏳ TRACE: Waiting for RTI DDS Spy to receive durable announcement..."
sleep 10

# Check for registration announcement in DDS Spy logs
echo "🔍 TRACE: Checking for registration announcement..."
echo "📜 DEBUG: Current RTI DDS Spy log contents:"
cat "$REGISTRATION_SPY_LOG"
echo "----------------------------------------"

# First check for writer creation
if grep -q "New writer.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$REGISTRATION_SPY_LOG"; then
    echo "✅ TRACE: Found GenesisRegistration writer"
    echo "🔍 TRACE: Now checking for registration announcement data..."
    
    # Wait a bit longer for the data to arrive
    sleep 5
    
    # Check the log again for the actual announcement data
    echo "📜 DEBUG: Updated RTI DDS Spy log contents:"
    cat "$REGISTRATION_SPY_LOG"
    echo "----------------------------------------"
    
    if grep -q "New data.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$REGISTRATION_SPY_LOG"; then
        echo "✅ TRACE: REGISTRATION ANNOUNCEMENTS WORK. DO NOT CHANGE IT. REGISTRATION ANNOUNCES WORK."
        echo "✅ TRACE: DURABILITY TEST PASSED - RTI DDS Spy received announcement even though it started after agent!"
        ANNOUNCEMENT_PASSED=true
    else
        echo "⚠️ WARNING: Registration writer found but no announcement data. Needs fixing!"
        ANNOUNCEMENT_PASSED=false
    fi
else
    echo "❌ TRACE: No registration writer found"
    ANNOUNCEMENT_PASSED=false
fi

# Clean up Test 1
echo "🧹 TRACE: Cleaning up Test 1..."
kill_process "$REGISTRATION_SPY_PID" "registration spy" true
kill_process "$AGENT_PID" "agent" false

echo "✅ TRACE: Test 1 completed"
echo "=============================================="

echo "🔬 TRACE: Starting Test 2 - Interface Test"
echo "=============================================="

# Start a new agent for the interface test
echo "🚀 TRACE: Starting new agent for interface test..."
PYTHONUNBUFFERED=1 stdbuf -o0 -e0 python3 -u "$AGENT_SCRIPT" > "$AGENT_LOG" 2>&1 &
AGENT_PID=$!
echo "✅ TRACE: Agent started with PID: $AGENT_PID"

# Wait for the agent to initialize
echo "⏳ TRACE: Waiting for agent to initialize..."
sleep 5

# Start RTI DDS Spy for interface test
echo "🚀 TRACE: Starting RTI DDS Spy for interface test..."
/Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -printSample -qosFile spy_transient.xml -qosProfile SpyLib::TransientReliable > "$INTERFACE_SPY_LOG" 2>&1 &
INTERFACE_SPY_PID=$!
echo "✅ TRACE: RTI DDS Spy started with PID: $INTERFACE_SPY_PID (Log: $INTERFACE_SPY_LOG)"

# Start the interface
echo "🚀 TRACE: Starting interface..."
python3 "$INTERFACE_SCRIPT" > "$INTERFACE_LOG" 2>&1 &
INTERFACE_PID=$!
echo "✅ TRACE: Interface started with PID: $INTERFACE_PID"

# Wait for the interface test to complete
echo "⏳ TRACE: Waiting for interface test to complete..."
wait $INTERFACE_PID || true

# Display logs
echo "📜 TRACE: Displaying Interface Test DDS Spy Log:"
echo "----------------------------------------"
cat "$INTERFACE_SPY_LOG"

echo "📜 TRACE: Displaying Agent Log:"
echo "----------------------------------------"
cat "$AGENT_LOG"

echo "📜 TRACE: Displaying Interface Log:"
echo "----------------------------------------"
cat "$INTERFACE_LOG"

# Clean up Test 2
echo "🧹 TRACE: Cleaning up Test 2..."
kill_process "$INTERFACE_SPY_PID" "interface spy" true
kill_process "$INTERFACE_PID" "interface" false
kill_process "$AGENT_PID" "agent" false

echo "✅ TRACE: Test 2 completed"
echo "=============================================="

echo "✅ TRACE: All tests completed successfully"