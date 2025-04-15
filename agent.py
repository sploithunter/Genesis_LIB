#!/usr/bin/env python3

import asyncio
import logging
from genesis_lib.agent import GenesisAgent
from genesis_lib.function_discovery import FunctionRegistry
from genesis_lib.datamodel import FunctionRequest, FunctionReply

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple_agent")

class SimpleAgent(GenesisAgent):
    def __init__(self):
        super().__init__("SimpleAgent", "SimpleService")
        logger.info("SimpleAgent initialized")
    
    async def process_request(self, request: FunctionRequest) -> FunctionReply:
        """
        Process incoming requests. This is a simple echo implementation.
        """
        logger.info(f"Processing request: {request}")
        return FunctionReply(
            success=True,
            result=request.parameters.get("message", ""),
            error_message=""
        )

async def main():
    try:
        # Initialize function registry
        registry = FunctionRegistry()
        
        # Create and start agent
        agent = SimpleAgent()
        logger.info("Agent started successfully")
        
        # Keep the agent running
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error in agent: {str(e)}")
        raise
    finally:
        if 'agent' in locals():
            await agent.close()

if __name__ == "__main__":
    asyncio.run(main()) 