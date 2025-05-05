from genesis_lib.openai_genesis_agent import OpenAIGenesisAgent
import os
import asyncio
import sys

class TestAgent(OpenAIGenesisAgent):
    def __init__(self):
        # Initialize the base class with our specific configuration
        super().__init__(
            model_name="gpt-4o",  # You can change this to your preferred model
            classifier_model_name="gpt-4o-mini",  # You can change this to your preferred model
            agent_name="TestAgent",  # Match the class name
            description="A test agent for monitoring and function tests",
            enable_tracing=True  # Enable tracing for testing
        )

async def main():
    # Create and run the agent
    agent = TestAgent()
    
    try:
        # Give some time for initialization and announcement propagation
        await asyncio.sleep(2)  # Use async sleep instead of time.sleep
        
        # Get message from command line argument or use default
        message = sys.argv[1] if len(sys.argv) > 1 else "Hello, can you tell me a joke?"
        
        # Example usage
        response = await agent.process_message(message)
        print(f"Agent response: {response}")
        
    finally:
        # Clean up using parent class cleanup
        await agent.close()

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 