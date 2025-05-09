#!/bin/bash

# Test for Interface -> Agent -> Service pipeline
# 1. Checks for clean DDS environment for relevant topics.
# 2. Starts SimpleGenesisAgent.
# 3. Starts CalculatorService.
# 4. Runs SimpleGenesisInterfaceStatic to send a math question.
# 5. Verifies the interaction through logs.

set -e # Exit immediately if a command exits with a non-zero status.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
LOG_DIR="$PROJECT_ROOT/logs"
PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Log files
AGENT_LOG="$LOG_DIR/test_sga_pipeline.log"
CALC_LOG="$LOG_DIR/test_calc_pipeline.log"
STATIC_INTERFACE_LOG="$LOG_DIR/test_static_interface_pipeline.log"
SPY_LOG="$LOG_DIR/test_pipeline_spy.log"

# PIDs of background processes
pids=()

# Cleanup function
cleanup() {
    echo "Cleaning up pipeline test processes..."
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Extra cleanup for rtiddsspy if it was left running
    pkill -f "rtiddsspy.*RegistrationAnnouncement" || true
    pkill -f "rtiddsspy.*InterfaceAgentRequest" || true
    pkill -f "rtiddsspy.*CalculatorServiceRequest" || true
    echo "Pipeline test cleanup complete."
}
trap cleanup EXIT

# --- 1. DDS Sanity Check ---
echo "Performing DDS sanity check for relevant topics..."
rm -f "$SPY_LOG"
# Spy on topics that should be quiet before our test starts
# We are checking for any writers or data on these specific topics.
# If your NDDSHOME is not set, this might not find rtiddsspy
NDDSHOME_PATH="${NDDSHOME:-/Applications/rti_connext_dds-7.3.0}" # Default if not set

if [ ! -f "$NDDSHOME_PATH/bin/rtiddsspy" ]; then
    echo "ERROR: rtiddsspy not found at $NDDSHOME_PATH/bin/rtiddsspy. Set NDDSHOME or adjust path."
    exit 1
fi

"$NDDSHOME_PATH/bin/rtiddsspy" -printSample -topic 'RegistrationAnnouncement' -topic 'InterfaceAgentRequest' -topic 'CalculatorServiceRequest' -duration 5 > "$SPY_LOG" 2>&1 &
SPY_PID=$!
pids+=("$SPY_PID") # Add spy to cleanup, though it should exit on its own
wait "$SPY_PID" # Wait for spy to finish its 5-second run

# Check if spy detected any activity on these specific topics
# We are looking for evidence of existing writers or data samples.
if grep -E '(New writer for topic|SAMPLE for topic)' "$SPY_LOG"; then
    echo "ERROR: DDS Sanity Check FAILED. Existing activity detected on RegistrationAnnouncement, InterfaceAgentRequest, or CalculatorServiceRequest topics."
    echo "Relevant spy log entries:"
    grep -E '(New writer for topic|SAMPLE for topic)' "$SPY_LOG"
    exit 1
else
    echo "DDS Sanity Check PASSED. No pre-existing activity on target topics."
fi
rm -f "$SPY_LOG" # Clean up the spy log for this check

# --- 2. Start SimpleGenesisAgent ---
echo "Starting SimpleGenesisAgent..."
python "$SCRIPT_DIR/simpleGenesisAgent.py" --tag pipeline_test > "$AGENT_LOG" 2>&1 &
pids+=("$!")

# --- 3. Start CalculatorService ---
echo "Starting CalculatorService..."
python "$PROJECT_ROOT/test_functions/calculator_service.py" --service-name PipelineCalcTest > "$CALC_LOG" 2>&1 &
pids+=("$!")

echo "Waiting 5 seconds for agent and service to initialize..."
sleep 5

# --- 4. Run SimpleGenesisInterfaceStatic ---
# It will use the question "What is 123 plus 456?" and expect 579
QUESTION_TO_ASK="What is 123 plus 456?"
EXPECTED_SUM=579

echo "Running SimpleGenesisInterfaceStatic with question: '$QUESTION_TO_ASK'..."
if python "$SCRIPT_DIR/simpleGenesisInterfaceStatic.py" --question "$QUESTION_TO_ASK" --verbose > "$STATIC_INTERFACE_LOG" 2>&1; then
    echo "SimpleGenesisInterfaceStatic completed successfully (exit code 0)."
else
    echo "ERROR: SimpleGenesisInterfaceStatic failed (exit code $?)."
    echo "--- Static Interface Log ($STATIC_INTERFACE_LOG) ---"
    cat "$STATIC_INTERFACE_LOG"
    echo "--- End Static Interface Log ---"
    exit 1
fi

# --- 5. Verify Interaction through Logs ---
echo "Verifying interactions via logs..."

# Check 1: Connected to SimpleGenesisAgent-pipeline_test
if ! grep -q "Successfully connected to agent: 'SimpleGenesisAgentForTheWin' (Service: 'OpenAIChat_pipeline_test')." "$STATIC_INTERFACE_LOG"; then
    echo "ERROR: Verification FAILED. Did not find print statement for connection to 'SimpleGenesisAgentForTheWin' (Service: 'OpenAIChat_pipeline_test') in $STATIC_INTERFACE_LOG"
    exit 1
fi
echo "  ✅ Verified: Connection to Agent (via print statement)."

# Check 2: Sent the correct question
# Escape quotes for grep pattern if question contains them (not in this case)
if ! grep -q "Sending to agent.*message': '$QUESTION_TO_ASK'" "$STATIC_INTERFACE_LOG"; then
    echo "ERROR: Verification FAILED. Did not find question '${QUESTION_TO_ASK}' being sent in $STATIC_INTERFACE_LOG"
    exit 1
fi
echo "  ✅ Verified: Question sent."

# Check 3: GenesisRPCClient log in CalculatorService log indicating correct function call and result
# The calculator_service.py uses GenesisRPCServer, but the *agent* uses GenesisRPCClient (via GenericFunctionClient)
# We need to check the *agent's* log for the client-side confirmation of the call to the calculator.
# The agent log ($AGENT_LOG) should show this via GenericFunctionClient -> GenesisRPCClient traces.
EXPECTED_RPC_CLIENT_LOG_PATTERN="GenesisRPCClient - INFO - Function add returned:.*{'result': $EXPECTED_SUM}"
if ! grep -qE "$EXPECTED_RPC_CLIENT_LOG_PATTERN" "$AGENT_LOG"; then
    echo "ERROR: Verification FAILED. Did not find RPC client confirmation of 'add' returning result $EXPECTED_SUM in $AGENT_LOG"
    echo "--- Agent Log ($AGENT_LOG) --- Tail:"
    tail -n 30 "$AGENT_LOG"
    echo "--- End Agent Log ---"
    exit 1
fi
echo "  ✅ Verified: RPC Client call to calculator service and correct raw result in agent log."

# Check 4: Final agent response in static interface log
# Example: Agent response: The sum of 123 and 456 is 579.
EXPECTED_AGENT_RESPONSE_PATTERN="Agent response: .*$EXPECTED_SUM"
if ! grep -qE "$EXPECTED_AGENT_RESPONSE_PATTERN" "$STATIC_INTERFACE_LOG"; then
    echo "ERROR: Verification FAILED. Did not find agent response containing '$EXPECTED_SUM' in $STATIC_INTERFACE_LOG"
    exit 1
fi
echo "  ✅ Verified: Final agent response contains correct sum."

echo "All pipeline verifications PASSED!"

# Cleanup is handled by trap
exit 0 