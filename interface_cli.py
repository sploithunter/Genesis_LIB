#!/usr/bin/env python3

import asyncio
import logging
import argparse
from genesis_lib.interface import GenesisInterface
from genesis_lib.datamodel import FunctionRequest, FunctionReply

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interface_cli")

# Use the same service name as the agent
SERVICE_NAME = "CalculatorService"

class SimpleInterface(GenesisInterface):
    def __init__(self):
        super().__init__("SimpleInterface", SERVICE_NAME)
        logger.info("SimpleInterface initialized")
    
    async def send_message(self, message: str) -> str:
        """
        Send a message to the agent and get the response
        """
        request = FunctionRequest(
            function_name="process_request",
            parameters={"message": message}
        )
        
        try:
            reply = await self.send_request(request)
            if isinstance(reply, FunctionReply) and reply.success:
                return reply.result
            else:
                return f"Error: {reply.error_message if reply else 'Unknown error'}"
        except Exception as e:
            return f"Error sending request: {str(e)}"

async def main():
    parser = argparse.ArgumentParser(description='Simple Genesis Interface CLI')
    parser.add_argument('--message', '-m', type=str, help='Message to send to the agent')
    args = parser.parse_args()
    
    try:
        # Create interface
        interface = SimpleInterface()
        
        # Wait for agent to be available
        if not await interface.wait_for_agent():
            logger.error("Failed to discover agent")
            return 1
        
        if args.message:
            # Send message and get response
            response = await interface.send_message(args.message)
            print(f"Response: {response}")
        else:
            # Interactive mode
            print("Entering interactive mode (type 'exit' to quit)")
            while True:
                message = input("> ")
                if message.lower() == 'exit':
                    break
                response = await interface.send_message(message)
                print(f"Response: {response}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in interface: {str(e)}")
        return 1
    finally:
        if 'interface' in locals():
            await interface.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code) 