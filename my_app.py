#!/usr/bin/env python3
"""
My Genesis Application
"""

import logging
from genesis_lib.monitored_agent import MonitoredAgent
from genesis_lib.interface import GenesisInterface
from genesis_lib.genesis_app import GenesisApp
from genesis_lib.function_client import GenericFunctionClient
from genesis_lib import genesis_monitoring

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class MyAgent(MonitoredAgent):
    """My custom agent."""
    
    def __init__(self, agent_name="MyAgent"):
        """Initialize the agent."""
        super().__init__(agent_name, "Test")  # Use Test service interface
        logger.info(f"Initialized {agent_name} with Test service")
    
    def _process_request(self, request):
        """Process the request and return a reply."""
        logger.info(f"Received request: {request}")
        
        # Create a simple reply
        reply = {
            "message": f"Hello from {self.agent_name}!",
            "status": 0  # 0 indicates success
        }
        
        logger.info(f"Sending reply: {reply}")
        return reply

def main():
    """Main function."""
    # Configure DDS logging
    logger, log_publisher, handler = genesis_monitoring.configure_dds_logging(
        logger_name="MyApp",
        source_name="MyAgent",
        log_level=logging.INFO
    )
    
    # Add DDS handler to root logger so all loggers get it
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    try:
        # Create an agent
        agent = MyAgent()
        
        # Run the agent
        agent.run()
    finally:
        # Clean up DDS logging
        log_publisher.close()

if __name__ == "__main__":
    main()
