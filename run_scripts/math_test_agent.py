#!/usr/bin/env python3
import logging
import asyncio
import sys
import traceback
import time
import uuid
import json
from genesis_lib.monitored_agent import MonitoredAgent

# Configure logging with detailed format
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger("MathTestAgent")

class MathTestAgent(MonitoredAgent):
    """
    A monitored agent for testing concurrent Interface <-> Agent RPC
    using simple math operations.
    """
    def __init__(self):
        logger.info("🏗️ TRACE: Creating MathTestAgent...")
        super().__init__(
            agent_name="MathTestAgent",
            service_name="ChatGPT",  # Use the same service name as baseline
            agent_id=str(uuid.uuid4())
        )

    async def _process_request(self, request) -> dict:
        """Process a request from an interface."""
        try:
            # Parse the JSON message from the request
            data = json.loads(request['message'])
            x = data['x']
            y = data['y']
            operation = data['operation']
            conversation_id = data['conversation_id']

            # Perform the requested operation
            if operation == 'add':
                result = x + y
            elif operation == 'subtract':
                result = x - y
            elif operation == 'multiply':
                result = x * y
            elif operation == 'divide':
                if y == 0:
                    return {
                        'message': 'Error: Division by zero',
                        'status': 1,
                        'conversation_id': conversation_id
                    }
                result = x / y
            else:
                return {
                    'message': f'Error: Unknown operation {operation}',
                    'status': 1,
                    'conversation_id': conversation_id
                }

            return {
                'message': str(result),
                'status': 0,
                'conversation_id': conversation_id
            }

        except json.JSONDecodeError as e:
            logger.error(f"💥 TRACE: Error decoding JSON message: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            return {
                'message': f'Error: Invalid JSON message: {e}',
                'status': 1,
                'conversation_id': ''
            }
        except KeyError as e:
            logger.error(f"💥 TRACE: Missing required field: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            return {
                'message': f'Error: Missing required field: {e}',
                'status': 1,
                'conversation_id': ''
            }
        except Exception as e:
            logger.error(f"💥 TRACE: Error processing request: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            return {
                'message': f'Error: {e}',
                'status': 1,
                'conversation_id': ''
            }

async def main():
    logger.info("🎬 TRACE: Starting main()")
    agent = None
    try:
        logger.info("🏗️ TRACE: Creating MathTestAgent instance")
        agent = MathTestAgent()
        
        logger.info("🔄 TRACE: Starting agent event loop")
        shutdown_event = asyncio.Event()
        
        # The agent's request handling runs via the Replier's listener mechanism,
        # which is set up in the base class __init__. We just need to keep the event loop running.
        logger.info("⏳ TRACE: Waiting for shutdown signal...")
        await shutdown_event.wait() # Keep running until interrupted
        
    except KeyboardInterrupt:
        logger.info("👋 TRACE: KeyboardInterrupt received, shutting down.")
    except Exception as e:
        logger.error(f"💥 TRACE: Fatal error in main: {e}")
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
    finally:
        if agent:
            logger.info("🧹 TRACE: Closing agent resources...")
            await agent.close()
            logger.info("✅ TRACE: Agent closed successfully")
        logger.info("👋 TRACE: main() ending")

if __name__ == "__main__":
    logger.info("🚀 TRACE: Script starting")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"💥 TRACE: Script error: {e}")
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
    logger.info("👋 TRACE: Script ending") 