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

from monitored_interface_cli import TracingMonitoredChatGPTInterface

# Configure logging with detailed format
log_file = os.path.join(project_root, 'logs', 'math_test_interface.log')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))

logger = logging.getLogger("MathTestInterface")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Also configure root logger to show output in console
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

class MathTestInterface:
    def __init__(self, interface_id):
        self.interface_id = interface_id
        self.interface = None
        self.conversation_id = str(uuid.uuid4())
        logger.info(f"🚀 TRACE: MathTestInterface {interface_id} starting - Conversation ID: {self.conversation_id}")

    async def run(self):
        try:
            logger.info("🏗️ TRACE: Creating MathService interface...")
            # Use the same interface class as the CLI for consistency
            interface = TracingMonitoredChatGPTInterface()

            logger.info(f"🔍 TRACE: Waiting for agent discovery...")
            # Run wait_for_agent in a thread pool since it's not async
            loop = asyncio.get_event_loop()
            if not await loop.run_in_executor(None, interface.wait_for_agent):
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
            # Run send_request in a thread pool since it's not async
            reply = await loop.run_in_executor(None, interface.send_request, test_request)
            
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
                interface.close()
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