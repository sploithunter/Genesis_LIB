#!/usr/bin/env python3

import os
import sys
import time
import asyncio
import subprocess
import signal
import logging
from typing import List, Optional

# Add the project root to PYTHONPATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("service_starter")

class ServiceStarter:
    def __init__(self):
        # Get the workspace directory (Genesis-LIB)
        self.workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.processes = []
        
    def start_service(self, service_name: str) -> Optional[subprocess.Popen]:
        """Start a service by name."""
        try:
            service_path = os.path.join(self.workspace_dir, "test_functions", f"{service_name}.py")
            if not os.path.exists(service_path):
                logger.error(f"Service file not found: {service_path}")
                return None
                
            process = subprocess.Popen(
                [sys.executable, service_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(process)
            logger.info(f"Started {service_name} with PID {process.pid}")
            return process
        except Exception as e:
            logger.error(f"Error starting {service_name}: {str(e)}")
            return None

    def start_cli_agent(self) -> Optional[subprocess.Popen]:
        """Start the CLI agent."""
        try:
            agent_path = os.path.join(self.workspace_dir, "interface_cli.py")
            if not os.path.exists(agent_path):
                logger.error(f"Agent file not found: {agent_path}")
                return None
                
            process = subprocess.Popen(
                [sys.executable, agent_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(process)
            logger.info(f"Started CLI agent with PID {process.pid}")
            return process
        except Exception as e:
            logger.error(f"Error starting CLI agent: {str(e)}")
            return None

    def cleanup(self):
        """Clean up all started processes."""
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
        self.processes.clear()

async def run_test_client():
    """Run a test client that makes requests to the services."""
    try:
        from genesis_lib.rpc_client import GenesisRPCClient
        
        # Test calculator service
        calc_client = GenesisRPCClient('CalculatorService')
        print('Waiting for calculator service to be available...')
        await calc_client.wait_for_service(timeout_seconds=30)  # Increased timeout
        result = await calc_client.call_function('add', x=10, y=20)
        print(f'Calculator test: 10 + 20 = {result}')
        
        # Test text processor service
        text_client = GenesisRPCClient('TextProcessorService')
        print('Waiting for text processor service to be available...')
        await text_client.wait_for_service(timeout_seconds=30)  # Increased timeout
        result = await text_client.call_function('count_words', text='This is a test sentence with seven words.')
        print(f'Text processor test: Word count = {result}')
        
        # Test letter counter service
        letter_client = GenesisRPCClient('LetterCounterService')
        print('Waiting for letter counter service to be available...')
        await letter_client.wait_for_service(timeout_seconds=30)  # Increased timeout
        result = await letter_client.call_function('count_letter', text='Hello World', letter='l')
        print(f'Letter counter test: Letter count = {result}')
        
        print('All service tests completed successfully')
    except Exception as e:
        logger.error(f"Error running test client: {str(e)}")
        raise

def main():
    starter = ServiceStarter()
    
    try:
        # Start services
        services = ["calculator_service", "letter_counter_service", "text_processor_service"]
        for service in services:
            starter.start_service(service)
            time.sleep(1)  # Give services time to start
            
        # Start CLI agent
        starter.start_cli_agent()
        
        # Wait for services to be ready
        time.sleep(3)
        
        # Run test client
        asyncio.run(run_test_client())
        logger.info("Test client completed successfully")
            
        # Clean up and exit
        starter.cleanup()
        return 0
            
    except KeyboardInterrupt:
        logger.info("Shutting down services...")
        starter.cleanup()
        return 0
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        starter.cleanup()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 