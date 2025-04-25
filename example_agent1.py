from genesis_lib.openai_genesis_agent import OpenAIGenesisAgent
import os
import asyncio
import sys

class ExampleAgent1(OpenAIGenesisAgent):
    def __init__(self):
        # Initialize the base class with our specific configuration
        super().__init__(
            model_name="gpt-4o",  # You can change this to your preferred model
            classifier_model_name="gpt-4o-mini",  # You can change this to your preferred model
            agent_name="ExampleAgent1",  # Match the class name
            description="An example agent using OpenAI's GPT model",
            enable_tracing=True  # Enable tracing for this example agent
        )

async def main():
    # Create and run the agent
    agent = ExampleAgent1()
    
    try:
        # Announce agent presence
        agent.app.announce_self()
        
        # Give some time for initialization
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
        
   