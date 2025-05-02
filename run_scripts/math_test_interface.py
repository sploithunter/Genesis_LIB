#!/usr/bin/env python3
import logging
import sys
import os
import time
import traceback
import asyncio
import random
import uuid
import json

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from genesis_lib.monitored_interface import MonitoredInterface

# Configure logging with detailed format
log_file = os.path.join(project_root, 'logs', 'math_test_interface.log')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))

logger = logging.getLogger("MathTestInterface")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# Also configure root logger to show output in console
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

class TracingGenesisInterface(MonitoredInterface):
    def __init__(self, interface_name: str, service_name: str):
        logger.info("Initializing %s interface for service %s", interface_name, service_name)
        super().__init__(interface_name=interface_name, service_name=service_name)
        logger.info("Interface initialization complete")
        
    async def wait_for_agent(self, timeout_seconds: int = 30) -> bool:
        """Override wait_for_agent to add tracing"""
        logger.info("Starting agent discovery wait")
        logger.debug("Interface DDS Domain ID from env: %s", os.getenv('ROS_DOMAIN_ID', 'Not Set'))
        logger.debug("Interface service name: %s", self.service_name)
        
        # Log participant info if available
        if hasattr(self.app, 'participant'):
            logger.debug("Interface DDS participant initialized")
            logger.debug("Interface DDS domain ID: %d", self.app.participant.domain_id)
        else:
            logger.warning("Interface participant not initialized")
        
        result = await super().wait_for_agent(timeout_seconds)
        if result:
            logger.info("Successfully discovered agent")
        else:
            logger.warning("Failed to discover agent within timeout")
        return result
        
    async def send_request(self, request: dict, timeout_seconds: float = 10.0) -> dict:
        """Override send_request to add tracing"""
        logger.info("Sending request to agent: %s", request)
        try:
            reply = await super().send_request(request, timeout_seconds)
            logger.info("Received reply from agent: %s", reply)
            return reply
        except Exception as e:
            logger.error("Error sending request: %s", str(e), exc_info=True)
            return None

class MathTestInterface:
    def __init__(self, interface_id):
        self.interface_id = interface_id
        self.interface = None
        self.conversation_id = str(uuid.uuid4())
        logger.info(f"🚀 TRACE: MathTestInterface {interface_id} starting - Conversation ID: {self.conversation_id}")

    async def run(self):
        try:
            logger.info("🏗️ TRACE: Creating MathService interface...")
            # Create interface with tracing
            interface = TracingGenesisInterface(interface_name="MathTestInterface", service_name="ChatGPT")

            logger.info(f"🔍 TRACE: Waiting for agent discovery...")
            if not await interface.wait_for_agent():
                logger.error(f"❌ TRACE: No agent found, exiting")
                return 1

            logger.info(f"✅ TRACE: Agent discovered successfully")
            
            # Generate random math operation
            operations = ['add', 'subtract', 'multiply', 'divide']
            operation = random.choice(operations)
            x = random.randint(1, 100)
            y = random.randint(1, 100)
            
            # Create test request using the same message structure as baseline
            test_request = {
                'message': json.dumps({
                    'x': x,
                    'y': y,
                    'operation': operation,
                    'conversation_id': self.conversation_id
                }),
                'conversation_id': self.conversation_id  # Add conversation_id at the top level for session tracking
            }
            
            logger.info(f"📤 TRACE: Sending math request: {test_request}")

            # Send the request using the existing interface method
            reply = await interface.send_request(test_request)
            
            if reply:
                logger.info(f"📥 TRACE: Received reply: {reply}")
                if reply.get('status') != 0:
                    logger.warning(f"⚠️ TRACE: Reply indicated error status: {reply['status']}")
                else:
                    # Parse the response
                    response_data = json.loads(reply['message'])
                    result = float(response_data)

                    # Calculate expected result
                    expected_result = self._calculate_expected_result(x, y, operation)

                    # Compare results
                    if abs(result - expected_result) < 0.0001:  # Use small epsilon for float comparison
                        logger.info(f"✅ TRACE: Math test passed - result={result}, expected={expected_result}")
                        return 0
                    else:
                        logger.error(f"❌ TRACE: Math test failed - result={result}, expected={expected_result}")
                        return 1
            else:
                logger.error("❌ TRACE: No reply received from agent")
                return 1

        except Exception as e:
            logger.error(f"❌ TRACE: Error in math test: {str(e)}")
            logger.error(traceback.format_exc())
            return 1
        finally:
            if interface:
                logger.info("🧹 TRACE: Cleaning up interface")
                await interface.close()
            logger.info(f"🏁 TRACE: MathTestInterface {self.interface_id} ending")

    def _calculate_expected_result(self, x, y, operation):
        if operation == 'add':
            return x + y
        elif operation == 'subtract':
            return x - y
        elif operation == 'multiply':
            return x * y
        elif operation == 'divide':
            return x / y
        return None

async def main():
    logger.info("🚀 TRACE: MathTestInterface starting")
    interface = MathTestInterface("Interface1")
    exit_code = await interface.run()
    logger.info(f"🏁 TRACE: MathTestInterface ending with exit code: {exit_code}")
    return exit_code

if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 