import logging
import os
from genesis_lib.agent import GenesisAgent, AnthropicChatAgent
import time
from typing import Any, Dict

# Configure logging for both app and library with detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG level for maximum detail
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Get logger for this file
logger = logging.getLogger(__name__)

class TracingAnthropicChatAgent(GenesisAgent, AnthropicChatAgent):
    """Custom implementation that combines GenesisAgent and AnthropicChatAgent directly"""
    def __init__(self, system_prompt: str):
        logger.info("Initializing TracingAnthropicChatAgent")
        # Initialize both parent classes
        GenesisAgent.__init__(self, agent_name="Claude", service_name="ChatGPT")
        AnthropicChatAgent.__init__(self, system_prompt=system_prompt)
        logger.info("Agent initialization complete")
        
    def run(self):
        """Override run to add tracing"""
        logger.info("Agent starting up - PID: %d", os.getpid())
        logger.debug("Agent DDS Domain ID from env: %s", os.getenv('ROS_DOMAIN_ID', 'Not Set'))
        logger.debug("Agent service name: %s", self.service_name)
        
        try:
            logger.info("Announcing agent presence")
            self.app.announce_self()
            
            # Now that we're initialized, we can log the participant info
            if hasattr(self.app, 'participant'):
                logger.debug("Agent DDS participant initialized")
                logger.debug("Agent DDS domain ID: %d", self.app.participant.domain_id)
                # Log any other participant info we might need later
            else:
                logger.warning("Agent participant not initialized")
            
            logger.info("Starting agent main loop")
            while True:
                time.sleep(0.1)  # Small sleep to prevent busy loop
                
        except Exception as e:
            logger.error("Error in agent run loop: %s", str(e), exc_info=True)
        finally:
            logger.info("Agent shutting down")
            
    def process_request(self, request: Any) -> Dict[str, Any]:
        """Process chat request using Claude"""
        message = request["message"]
        response, status = self.generate_response(message, "default")
        return {
            "message": response,
            "status": status
        }

def main():
    """Main function with enhanced tracing"""
    logger.info("Agent main() starting")
    try:
        agent = TracingAnthropicChatAgent(
            system_prompt="You are a helpful AI assistant."
        )
        logger.info("Created agent instance successfully")
        agent.run()
    except Exception as e:
        logger.error("Fatal error in main: %s", str(e), exc_info=True)
    finally:
        logger.info("Agent main() ending")

if __name__ == "__main__":
    main()
