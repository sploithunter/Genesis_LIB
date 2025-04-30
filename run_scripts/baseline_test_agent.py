#!/usr/bin/env python3
import logging
import asyncio
import sys
import traceback
import time
from genesis_lib.monitored_agent import MonitoredAgent

# Configure logging with detailed format
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger("BaselineTestAgent")

class BaselineTestAgent(MonitoredAgent):
    """
    A simple monitored agent for baseline testing of Interface <-> Agent RPC
    using the 'ChatGPT' service name and existing request/reply types.
    """
    def __init__(self):
        logger.info("🚀 TRACE: Starting BaselineTestAgent initialization...")
        try:
            super().__init__(
                agent_name="BaselineTestAgent",
                service_name="ChatGPT",  # Use the service name the interface expects
                agent_type="AGENT",      # Standard agent type
                description="Baseline agent for testing Interface RPC"
            )
            logger.info("✅ TRACE: BaselineTestAgent initialized successfully")
        except Exception as e:
            logger.error(f"💥 TRACE: Error during initialization: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            raise

    async def _process_request(self, request) -> dict:
        """
        Handles incoming requests for the 'ChatGPT' service.
        Returns a fixed joke response.
        """
        logger.info(f"📥 TRACE: Received request: {request}")
        try:
            # Extract message and conversation_id from the DynamicData object
            message = request['message']
            conversation_id = request['conversation_id']
            logger.info(f"📝 TRACE: Processing request - message='{message}', conversation_id='{conversation_id}'")

            # Fixed joke response
            reply_message = "Why don't scientists trust atoms? Because they make up everything!"
            status = 0 # Success

            logger.info(f"📤 TRACE: Sending reply - message='{reply_message}', status={status}")
            # Return structure must match ChatGPTReply
            return {
                'message': reply_message,
                'status': status,
                'conversation_id': conversation_id # Echo back conversation ID if present
            }
        except Exception as e:
            logger.error(f"💥 TRACE: Error processing request: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            raise

async def main():
    logger.info("🎬 TRACE: Starting main()")
    agent = None
    try:
        logger.info("🏗️ TRACE: Creating BaselineTestAgent instance")
        agent = BaselineTestAgent()
        
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