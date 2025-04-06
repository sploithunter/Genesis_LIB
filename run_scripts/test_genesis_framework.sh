#!/bin/bash

# Genesis Framework Test Suite
# This script runs comprehensive tests for the Genesis distributed framework

# Source the setup script to set environment variables
echo "===== Sourcing setup.sh ====="
source setup.sh

# Create logs directory if it doesn't exist
mkdir -p logs

# Get current timestamp for log files
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MAIN_LOG_FILE="logs/genesis_framework_test_${TIMESTAMP}.log"
SERVICES_LOG_FILE="logs/services_test_${TIMESTAMP}.log"

echo "===== Starting Genesis Framework Test Suite ====="
echo "Date: $(date)"
echo "Main log file: ${MAIN_LOG_FILE}"
echo "Services log file: ${SERVICES_LOG_FILE}"

# Function to log messages to both console and log file
log_message() {
    echo "$1" | tee -a ${MAIN_LOG_FILE}
}

# Function to check if a process is running
check_process() {
    if ps -p $1 > /dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to run service tests
run_service_tests() {
    log_message "===== Running Service Tests ====="
    
    # Start multiple calculator services
    log_message "Starting Calculator Service instances..."
    python3 test_functions/calculator_service.py &
    CALCULATOR_PID_1=$!
    python3 test_functions/calculator_service.py &
    CALCULATOR_PID_2=$!
    python3 test_functions/calculator_service.py &
    CALCULATOR_PID_3=$!
    
    # Start letter counter service
    log_message "Starting Letter Counter Service..."
    python3 test_functions/letter_counter_service.py &
    LETTER_COUNTER_PID=$!
    
    # Start text processor service
    log_message "Starting Text Processor Service..."
    python3 test_functions/text_processor_service.py &
    TEXT_PROCESSOR_PID=$!
    
    # Wait for services to initialize
    log_message "Waiting for services to initialize..."
    sleep 10
    
    # Verify all services are running
    local all_services_running=true
    for pid in ${CALCULATOR_PID_1} ${CALCULATOR_PID_2} ${CALCULATOR_PID_3} ${LETTER_COUNTER_PID} ${TEXT_PROCESSOR_PID}; do
        if ! check_process ${pid}; then
            log_message "ERROR: Service with PID ${pid} failed to start"
            all_services_running=false
        fi
    done
    
    if [ "$all_services_running" = false ]; then
        log_message "Service startup verification failed"
        return 1
    fi
    
    # Run the service tests
    log_message "Running service test suite..."
    python3 test_functions/test_all_services.py | tee -a ${SERVICES_LOG_FILE}
    local test_result=$?
    
    # Stop all services
    log_message "Stopping services..."
    for pid in ${CALCULATOR_PID_1} ${CALCULATOR_PID_2} ${CALCULATOR_PID_3}; do
        kill ${pid} 2>/dev/null || true
        wait ${pid} 2>/dev/null || true
    done
    
    kill ${LETTER_COUNTER_PID} 2>/dev/null || true
    wait ${LETTER_COUNTER_PID} 2>/dev/null || true
    
    kill ${TEXT_PROCESSOR_PID} 2>/dev/null || true
    wait ${TEXT_PROCESSOR_PID} 2>/dev/null || true
    
    return ${test_result}
}

# Function to run DDS communication tests
run_dds_tests() {
    log_message "===== Running DDS Communication Tests ====="
    
    # Test DDS domain participant creation
    log_message "Testing DDS domain participant creation..."
    python3 -c "
from genesis_lib.dds_domain import DDSDomain
try:
    domain = DDSDomain()
    domain.initialize()
    print('DDS domain participant creation: SUCCESS')
    domain.cleanup()
except Exception as e:
    print(f'DDS domain participant creation: FAILED - {str(e)}')
    exit(1)
" | tee -a ${MAIN_LOG_FILE}
    
    local test_result=$?
    if [ ${test_result} -ne 0 ]; then
        log_message "DDS communication tests failed"
        return 1
    fi
    
    return 0
}

# Function to run RPC framework tests
run_rpc_tests() {
    log_message "===== Running RPC Framework Tests ====="
    
    # Test RPC client/service creation
    log_message "Testing RPC client/service creation..."
    python3 -c "
from genesis_lib.rpc_client import GenesisRPCClient
from genesis_lib.rpc_service import GenesisRPCService
try:
    client = GenesisRPCClient('TestService')
    service = GenesisRPCService('TestService')
    print('RPC client/service creation: SUCCESS')
    client.cleanup()
    service.cleanup()
except Exception as e:
    print(f'RPC client/service creation: FAILED - {str(e)}')
    exit(1)
" | tee -a ${MAIN_LOG_FILE}
    
    local test_result=$?
    if [ ${test_result} -ne 0 ]; then
        log_message "RPC framework tests failed"
        return 1
    fi
    
    return 0
}

# Main test execution
main() {
    local overall_result=0
    
    # Run DDS communication tests
    run_dds_tests
    if [ $? -ne 0 ]; then
        log_message "DDS tests failed"
        overall_result=1
    fi
    
    # Run RPC framework tests
    run_rpc_tests
    if [ $? -ne 0 ]; then
        log_message "RPC tests failed"
        overall_result=1
    fi
    
    # Run service tests
    run_service_tests
    if [ $? -ne 0 ]; then
        log_message "Service tests failed"
        overall_result=1
    fi
    
    # Print final results
    log_message "===== Test Suite Complete ====="
    if [ ${overall_result} -eq 0 ]; then
        log_message "All tests passed successfully"
    else
        log_message "Some tests failed - check logs for details"
    fi
    
    return ${overall_result}
}

# Run the test suite
main
exit $? 