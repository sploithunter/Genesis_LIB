import asyncio
import logging
import sys
import argparse # Added for command-line arguments
from genesis_lib.monitored_interface import MonitoredInterface
from genesis_lib.logging_config import set_genesis_library_log_level # Import the new utility

# Logger will be configured in main() after parsing args
logger = logging.getLogger("SimpleGenesisInterfaceCLI")

INTERFACE_NAME = "SimpleCLI-111"
# AGENT_SERVICE_NAME is no longer a fixed target for initial connection filtering.
# The user will select an agent, and its specific service_name will be used.

async def main(verbose: bool = False): # Added verbose parameter
    # Configure basic logging for this script
    log_level = logging.DEBUG if verbose else logging.INFO
    # Application script configures its own root logger and its desired level
    logging.basicConfig(
        level=log_level, # This sets the default for all loggers unless overridden
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # If verbose mode is enabled for the script, also make genesis_lib verbose.
    # Otherwise, genesis_lib loggers will respect the script's root logger setting (e.g., INFO).
    # We previously changed noisy INFOs in the library to DEBUGs, so this should be cleaner.
    if verbose:
        set_genesis_library_log_level(logging.DEBUG)
        # The lines below are now handled by set_genesis_library_log_level
        # logging.getLogger("genesis_lib.monitored_interface").setLevel(logging.DEBUG)
        # logging.getLogger("genesis_lib.interface").setLevel(logging.DEBUG)
        # logging.getLogger("genesis_app").setLevel(logging.DEBUG)
    # else:
        # Optional: If you wanted genesis_lib to be *quieter* than the script by default
        # (e.g. script is INFO, but library is WARNING unless script is DEBUG)
        # you could add: set_genesis_library_log_level(logging.WARNING)
        # But for now, let them inherit the script's level or be DEBUG if script is verbose.

    logger.info(f"Initializing '{INTERFACE_NAME}' (Log Level: {logging.getLevelName(log_level)})...")
    # Initialize the MonitoredInterface. The service_name here is more of a default
    # or for how the interface itself might be identified, not for filtering agents initially.
    interface = MonitoredInterface(
        interface_name=INTERFACE_NAME,
        service_name="GenericInterfaceService" # Can be a generic name for the interface itself
    )

    target_agent_id = None
    target_agent_service_name = None
    connected_agent_name = "N/A"

    try:
        print("Waiting for any agent(s) to become available (up to 30s)...")
        try:
            await asyncio.wait_for(interface._agent_found_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Timeout: No agent discovery signal received within 30 seconds. Exiting.")
            await interface.close()
            return

        print("First agent(s) found. Waiting a moment for others to appear...")
        await asyncio.sleep(2)

        if not interface.available_agents:
            logger.error("No agents were discovered even after waiting. Exiting.")
            await interface.close()
            return

        print("Available agents:")
        agent_list = list(interface.available_agents.values())
        for i, agent_info in enumerate(agent_list):
            print(f"  {i+1}. Name: '{agent_info.get('prefered_name', 'N/A')}', ID: '{agent_info.get('instance_id')}', Service: '{agent_info.get('service_name')}'")

        if not agent_list:
            logger.error("No agents available to select. Exiting.")
            await interface.close()
            return

        selected_index = -1
        while True:
            try:
                choice = await asyncio.to_thread(input, "Select agent by number: ")
                selected_index = int(choice) - 1
                if 0 <= selected_index < len(agent_list):
                    selected_agent = agent_list[selected_index]
                    target_agent_id = selected_agent.get('instance_id')
                    target_agent_service_name = selected_agent.get('service_name')
                    connected_agent_name = selected_agent.get('prefered_name', target_agent_id)
                    break
                else:
                    print("Invalid selection. Please enter a number from the list.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except RuntimeError:
                print("Input stream closed during selection.")
                await interface.close()
                return
        
        if not target_agent_id or not target_agent_service_name:
            logger.error("Failed to select a valid agent or retrieve its details. Exiting.")
            await interface.close()
            return

        print(f"Attempting to connect to agent '{connected_agent_name}' (ID: {target_agent_id}) offering service '{target_agent_service_name}'...")
        
        connection_successful = await interface.connect_to_agent(
            service_name=target_agent_service_name,
            timeout_seconds=10.0
        )
        
        if connection_successful:
            interface._connected_agent_id = target_agent_id

        if not connection_successful:
            logger.error(f"Failed to establish RPC connection with agent '{connected_agent_name}' for service '{target_agent_service_name}'. Exiting.")
            await interface.close()
            return

        print(f"Successfully connected to agent: '{connected_agent_name}' (Service: '{target_agent_service_name}').")
        print("You can now send messages. Type 'quit' or 'exit' to stop.")

        while True:
            try:
                user_input = await asyncio.to_thread(input, f"To [{connected_agent_name}]: ")
            except RuntimeError:
                print("Input stream closed.")
                break
                
            if user_input.lower() in ['quit', 'exit']:
                print("User requested exit.")
                break

            if not user_input:
                continue

            request_data = {"message": user_input}
            logger.info(f"Sending to agent: {request_data}")
            
            response = await interface.send_request(request_data, timeout_seconds=20.0)
            
            if response:
                print(f"Agent response: {response.get('message', 'No message content in response')}")
                if response.get('status', -1) != 0:
                    logger.warning(f"Agent indicated an issue with status: {response.get('status')}")
            else:
                logger.error("No response from agent or request timed out.")
                if interface._connected_agent_id and interface._connected_agent_id not in interface.available_agents:
                     logger.error("Connection lost: The agent may have departed. Please restart the CLI.")
                     break

    except KeyboardInterrupt:
        print("\\nKeyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        print(f"Closing '{INTERFACE_NAME}' and releasing resources...")
        if 'interface' in locals() and interface:
            await interface.close()
        print(f"'{INTERFACE_NAME}' has been shut down.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Simple Genesis Interface CLI.")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level) for the CLI and Genesis libraries."
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(verbose=args.verbose)) # Pass verbose flag to main
    except KeyboardInterrupt:
        logger.info("CLI terminated by user.")
    sys.exit(0)
