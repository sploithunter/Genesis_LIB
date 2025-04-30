import time
import sys
import logging
import os

from genesis_lib.monitored_interface import MonitoredInterface

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

class TracingMonitoredInterface(MonitoredInterface):
    def __init__(self, interface_name: str, service_name: str):
        logger.info("Initializing %s interface for service %s", interface_name, service_name)
        super().__init__(interface_name=interface_name, service_name=service_name)
        logger.info("Interface initialization complete")
        
    def wait_for_agent(self) -> bool:
        """Override wait_for_agent to add tracing"""
        logger.info("Starting agent discovery wait")
        logger.debug("Interface DDS Domain ID from env: %s", os.getenv('ROS_DOMAIN_ID', 'Not Set'))
        logger.debug("Interface service name: %s", self.service_name)
        
        # Log participant info if available
        if hasattr(self.app, 'participant'):
            logger.debug("Interface DDS participant initialized")
            logger.debug("Interface DDS domain ID: %d", self.app.participant.domain_id)
            # Log any other participant info we might need later
        else:
            logger.warning("Interface participant not initialized")
        
        result = super().wait_for_agent()
        if result:
            logger.info("Successfully discovered agent")
        else:
            logger.warning("Failed to discover agent within timeout")
        return result
        
    def send_request(self, request: dict) -> dict:
        """Override send_request to add tracing"""
        logger.info("Sending request to agent: %s", request)
        try:
            reply = super().send_request(request)
            logger.info("Received reply from agent: %s", reply)
            return reply
        except Exception as e:
            logger.error("Error sending request: %s", str(e), exc_info=True)
            return None

class TracingMonitoredEchoInterface(TracingMonitoredInterface):
    def __init__(self):
        logger.info("Creating Echo interface")
        super().__init__(interface_name="InterfaceCLI", service_name="Echo")

class TracingMonitoredChatGPTInterface(TracingMonitoredInterface):
    def __init__(self, service_name="ChatGPT"):
        logger.info("Creating ChatGPT interface for service %s", service_name)
        super().__init__(interface_name="ChatGPTInterfaceCLI", service_name=service_name)

def main():
    logger.info("Interface main() starting - PID: %d", os.getpid())
    
    # Let user choose which interface to use
    print("Choose interface:")
    print("1. Echo")
    print("2. ChatGPT")
    
    choice = input("Enter choice (1 or 2): ")
    logger.info("User selected interface choice: %s", choice)
    
    try:
        if choice == "1":
            interface = TracingMonitoredEchoInterface()
            prompt_text = "Enter message to echo"
        elif choice == "2":
            interface = TracingMonitoredChatGPTInterface()
            prompt_text = "Enter message for ChatGPT"
        else:
            logger.error("Invalid choice selected: %s", choice)
            print("Invalid choice")
            sys.exit(1)
        
        # Announce presence and wait for agent
        logger.info("Announcing interface presence")
        interface.app.announce_self()
        
        if not interface.wait_for_agent():
            logger.error("No agent found, exiting")
            sys.exit(1)
        
        # Main loop
        logger.info("Starting main interface loop")
        while True:
            message = input(f"\n{prompt_text} (or 'quit' to exit): ")
            if message.lower() == 'quit':
                logger.info("User requested quit")
                break
                
            reply = interface.send_request({'message': message})
            if reply:
                print(f"Reply: {reply['message']}")
                if reply['status'] != 0:
                    logger.warning("Reply indicated error status: %d", reply['status'])
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        print("\nShutting down...")
    except Exception as e:
        logger.error("Unexpected error: %s", str(e), exc_info=True)
    finally:
        logger.info("Cleaning up interface")
        interface.close()
        logger.info("Interface main() ending")
        sys.exit(0)

if __name__ == "__main__":
    main() 