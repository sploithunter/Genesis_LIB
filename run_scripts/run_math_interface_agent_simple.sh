#!/bin/bash

# Script to run simple Interface <-> Agent RPC test with DDS tracing

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# Ensure we are in the run_scripts directory
cd "$SCRIPT_DIR"

# Set up log directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# Clear existing log files
echo "🧹 TRACE: Clearing existing log files..."
rm -f "$LOG_DIR/rtiddsspy_math.log"
rm -f "$LOG_DIR/math_test_agent.log"
rm -f "$LOG_DIR/math_test_interface.log"

# Define script and log file names
AGENT_SCRIPT="$PROJECT_ROOT/run_scripts/math_test_agent.py"
INTERFACE_SCRIPT="$PROJECT_ROOT/run_scripts/math_test_interface.py"
AGENT_LOG="$LOG_DIR/math_test_agent.log"
INTERFACE_LOG="$LOG_DIR/math_test_interface.log"
SPY_LOG="$LOG_DIR/rtiddsspy_math.log"

# Process IDs
AGENT_PID=""
INTERFACE_PID=""
SPY_PID=""

# Cleanup function to ensure processes are killed
cleanup() {
    echo "🧹 TRACE: Starting cleanup process..."
    if [ -n "$AGENT_PID" ]; then
        echo "🔫 TRACE: Stopping agent process $AGENT_PID..."
        kill $AGENT_PID 2>/dev/null || true
        wait $AGENT_PID 2>/dev/null || true
    fi
    if [ -n "$INTERFACE_PID" ]; then
        echo "🔫 TRACE: Stopping interface process $INTERFACE_PID..."
        kill $INTERFACE_PID 2>/dev/null || true
        wait $INTERFACE_PID 2>/dev/null || true
    fi
    if [ -n "$SPY_PID" ]; then
        echo "🔫 TRACE: Stopping RTI DDS Spy process $SPY_PID..."
        kill $SPY_PID 2>/dev/null || true
        wait $SPY_PID 2>/dev/null || true
    fi
    echo "✅ TRACE: Cleanup completed successfully"
}

# Set trap for cleanup on exit
trap cleanup EXIT INT TERM

# Start RTI DDS Spy with print sample
echo "🚀 TRACE: Starting RTI DDS Spy..."
/Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -printSample > "$SPY_LOG" 2>&1 &
SPY_PID=$!
echo "✅ TRACE: RTI DDS Spy started with PID: $SPY_PID (Log: $SPY_LOG)"

# Wait a moment for the spy to initialize
echo "⏳ TRACE: Waiting for RTI DDS Spy to initialize..."
sleep 2

# Run the agent in the background
echo "🚀 TRACE: Starting Math Test Agent in background..."
PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" python "$AGENT_SCRIPT" > "$AGENT_LOG" 2>&1 &
AGENT_PID=$!
echo "✅ TRACE: Agent started with PID: $AGENT_PID (Log: $AGENT_LOG)"

# Wait for the agent to initialize
echo "⏳ TRACE: Waiting 3 seconds for agent to initialize..."
sleep 3

# Run single interface instance
echo "🚀 TRACE: Starting Math Test Interface..."
PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" python "$INTERFACE_SCRIPT" > "$INTERFACE_LOG" 2>&1 &
INTERFACE_PID=$!
echo "✅ TRACE: Interface started with PID: $INTERFACE_PID (Log: $INTERFACE_LOG)"

# Wait for the interface to complete
echo "⏳ TRACE: Waiting for interface to complete..."
if wait $INTERFACE_PID; then
    echo "✅ TRACE: Interface completed successfully"
else
    echo "❌ TRACE: Interface failed"
    exit 1
fi

# Wait a moment to ensure all DDS messages are captured
echo "⏳ TRACE: Waiting for final DDS messages..."
sleep 2

# Display the logs
echo -e "\n📜 TRACE: Displaying RTI DDS Spy Log:"
echo "----------------------------------------"
cat "$SPY_LOG"
echo -e "\n📜 TRACE: Displaying Agent Log:"
echo "----------------------------------------"
cat "$AGENT_LOG"
echo -e "\n📜 TRACE: Displaying Interface Log:"
echo "----------------------------------------"
cat "$INTERFACE_LOG"

# Check for registration announcement in DDS Spy logs
echo "🔍 TRACE: Checking for registration announcement in DDS Spy logs..."
if grep -A 4 "New data.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$SPY_LOG" | \
   grep -q "message: \"Agent MathTestAgent announcing presence\"" && \
   grep -A 4 "New data.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$SPY_LOG" | \
   grep -q "prefered_name: \"MathTestAgent\"" && \
   grep -A 4 "New data.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$SPY_LOG" | \
   grep -q "default_capable: 1" && \
   grep -A 4 "New data.*topic=\"GenesisRegistration\".*type=\"genesis_agent_registration_announce\"" "$SPY_LOG" | \
   grep -q "instance_id: \"[0-9a-f-]\{36\}\""; then
    echo "✅ TRACE: Registration announcement found with all expected fields"
else
    echo "❌ TRACE: Registration announcement not found or missing expected fields"
    exit 1
fi

echo "✅ TRACE: Test completed successfully"
exit 0 