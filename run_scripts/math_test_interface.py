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
from genesis_lib.logging_config import configure_genesis_logging

# Configure logging using common configuration
logger = configure_genesis_logging("MathTestInterface", "MathTestInterface", logging.INFO)

class MathTestInterface:
    def __init__(self, interface_id):
        self.interface_id = interface_id
        self.interface = None
        self.conversation_id = str(uuid.uuid4())
        logger.info(f"🚀 TRACE: MathTestInterface {interface_id} starting - Conversation ID: {self.conversation_id}")

    async def run(self):
        interface = None # Ensure interface is defined in outer scope for finally block
        try:
            logger.info("🏗️ TRACE: Creating MathService interface...")
            # Create interface - now using MonitoredInterface directly
            interface = MonitoredInterface(interface_name="MathTestInterface", service_name="ChatGPT")

            logger.info(f"🔍 TRACE: Waiting for agent discovery event...")
            try:
                await asyncio.wait_for(interface._agent_found_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error(f"❌ TRACE: Timeout waiting for any agent to be discovered.")
                if interface: await interface.close()
                return 1

            # Select the first agent discovered (simple strategy for testing)
            chosen_agent = None
            if interface.available_agents:
                 chosen_agent = list(interface.available_agents.values())[0]
                 logger.info(f"✅ TRACE: Agent discovered. Selecting first available: {chosen_agent['prefered_name']}")
            else:
                logger.error("❌ TRACE: Agent found event triggered, but no agents in available list?!")
                if interface: await interface.close()
                return 1
                
            # Connect to the chosen agent
            logger.info(f"🔗 TRACE: Attempting to connect to service: {chosen_agent['service_name']}")
            if not await interface.connect_to_agent(chosen_agent['service_name'], timeout_seconds=10.0):
                logger.error(f"❌ TRACE: Failed to connect to agent service {chosen_agent['service_name']}")
                if interface: await interface.close()
                return 1
                
            # Store the ID of the connected agent for departure handling
            interface._connected_agent_id = chosen_agent['instance_id']
            logger.info(f"✅ TRACE: Successfully connected to agent: {chosen_agent['prefered_name']} (ID: {interface._connected_agent_id})")
            
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
                # Check if the agent departed during the request
                if interface and not interface._connected_agent_id:
                    logger.error("❌ TRACE: No reply received, and the connected agent has departed.")
                else:
                    logger.error("❌ TRACE: No reply received from agent (agent might still be connected). Check agent logs.")
                return 1

        except Exception as e:
            logger.error(f"❌ TRACE: Error in math test: {str(e)}")
            logger.error(traceback.format_exc())
            # Ensure cleanup happens even on unexpected error
            if interface:
                try:
                    await interface.close()
                except Exception as close_e:
                    logger.error(f"❌ TRACE: Error during cleanup: {close_e}")
            return 1 # Indicate failure
        finally:
            # Ensure interface is closed cleanly even if run completes successfully or errors out early
            if interface: 
                logger.info("🧹 TRACE: Cleaning up interface (finally block)")
                try:
                    await interface.close()
                except Exception as final_close_e:
                     logger.error(f"❌ TRACE: Error during final interface cleanup: {final_close_e}")

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