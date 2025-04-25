from genesis_lib.openai_genesis_agent import OpenAIGenesisAgent
import os
import asyncio
import logging
import time
from functools import partial
import traceback
import uuid

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG for more verbose output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExampleAgent1(OpenAIGenesisAgent):
    def __init__(self):
        logger.info("===== TRACING: Starting ExampleAgent1 initialization =====")
        
        # Set agent_id before initialization
        self.agent_id = str(uuid.uuid4())
        
        # Initialize the base class with our specific configuration
        super().__init__(
            model_name="gpt-4o",  # You can change this to your preferred model
            classifier_model_name="gpt-4o-mini",  # You can change this to your preferred model
            agent_name="ExampleAgent1",  # Match the class name
            description="An example agent using OpenAI's GPT model"
        )
        
        # Set up OpenAI configuration
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        # Initialize agent capabilities
        self.agent_capabilities = {
            "models": {
                "main": self.model_name,
                "classifier": self.classifier_model_name
            },
            "functions": [],  # Will be populated during function discovery
            "supported_tasks": ["text_generation", "conversation"]
        }
        
        logger.info("===== TRACING: ExampleAgent1 initialized successfully =====")
        
    async def process_message(self, message: str) -> str:
        """
        Process a message using OpenAI and return the response.
        This method is monitored by the Genesis framework.
        """
        logger.info(f"===== TRACING: Processing message: {message} =====")
        try:
            # Process the message using OpenAI's process_request method
            logger.info("===== TRACING: Calling process_request =====")
            response = await self.process_request({"message": message})
            logger.info(f"===== TRACING: Received response: {response} =====")
            
            # Publish a monitoring event for the successful response
            logger.info("===== TRACING: Publishing monitoring event =====")
            self.publish_monitoring_event(
                event_type="AGENT_RESPONSE",
                result_data={"response": response}
            )
            
            return response.get("message", "No response generated")
            
        except Exception as e:
            logger.error(f"===== TRACING: Error processing message: {str(e)} =====")
            # Publish a monitoring event for the error
            self.publish_monitoring_event(
                event_type="AGENT_STATUS",
                status_data={"error": str(e)}
            )
            raise

    async def cleanup(self):
        """Async cleanup that properly handles both async and sync operations"""
        logger.info("===== TRACING: Starting cleanup =====")
        try:
            # Clean up OpenAI-specific resources first
            if hasattr(self, 'generic_client') and self.generic_client is not None:
                logger.info("===== TRACING: Closing generic client =====")
                if asyncio.iscoroutinefunction(self.generic_client.close):
                    await self.generic_client.close()
                else:
                    self.generic_client.close()
            
            # Call parent class cleanup
            logger.info("===== TRACING: Running parent cleanup =====")
            await super().close()
            
        except Exception as e:
            logger.error(f"===== TRACING: Error during cleanup: {e} =====")
            logger.error(traceback.format_exc())

async def main():
    logger.info("===== TRACING: Starting main function =====")
    # Create and run the agent
    agent = ExampleAgent1()
    
    try:
        # Announce agent presence
        logger.info("===== TRACING: Announcing agent presence =====")
        agent.app.announce_self()
        
        # Give some time for initialization
        logger.info("===== TRACING: Waiting for initialization =====")
        await asyncio.sleep(2)  # Use async sleep instead of time.sleep
        
        # Example usage
        logger.info("===== TRACING: Sending test message =====")
        response = await agent.process_message("Hello, can you tell me a joke?")
        print(f"Agent response: {response}")
        
    except Exception as e:
        logger.error(f"===== TRACING: Error during agent execution: {e} =====")
        raise
    finally:
        # Clean up using our async cleanup method
        logger.info("===== TRACING: Starting cleanup =====")
        await agent.cleanup()

if __name__ == "__main__":
    # Run the async main function
    logger.info("===== TRACING: Starting agent =====")
    asyncio.run(main())
        
   