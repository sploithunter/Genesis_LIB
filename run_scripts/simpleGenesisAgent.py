from genesis_lib.openai_genesis_agent import OpenAIGenesisAgent
import asyncio
import logging # Added for script-level logging
import argparse # Added for command-line arguments

# Configure basic logging for this script
# logging.basicConfig(
#     level=logging.INFO, 
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
logger = logging.getLogger("SimpleGenesisAgentScript")

class SimpleGenesisAgent(OpenAIGenesisAgent):
    def __init__(self, service_instance_tag: str = None): # Added service_instance_tag
        # Initialize the base class with our specific configuration
        super().__init__(
            model_name="gpt-4o",  # You can change this to your preferred model
            classifier_model_name="gpt-4o-mini",  # You can change this to your preferred model
            agent_name="SimpleGenesisAgentForTheWin",  # Friendly name for this agent instance
            # base_service_name="MyCustomChatService", # Optional: Override default OpenAIChat
            service_instance_tag=service_instance_tag,     # Pass the tag
            description="A simple agent that listens for messages via Genesis interface and processes them.", 
            enable_tracing=True  # Enable tracing for testing
        )
        # The base class (OpenAIGenesisAgent) also has its own logging for initialization details
        logger.info(f"'{self.agent_name}' instance (tag: {service_instance_tag or 'default'}) created. RPC Service: '{self.rpc_service_name}'. Ready to connect to Genesis services.")

async def main(tag: str = None, verbose: bool = False): # Added verbose parameter
    print(f"###### AGENT MAIN STARTED - Tag: {tag}, Verbose: {verbose} ######") 
    # ---- START DIAGNOSTIC BLOCK ----
    # import logging # logging is already imported at the top of the file
    root_logger = logging.getLogger()
    print(f"###### Root logger level: {logging.getLevelName(root_logger.level)} ######")
    print(f"###### Root logger handlers: {root_logger.handlers} ######")
    script_logger = logging.getLogger("SimpleGenesisAgentScript")
    print(f"###### Script logger effective level: {logging.getLevelName(script_logger.getEffectiveLevel())} ######")
    print(f"###### Script logger handlers: {script_logger.handlers} ######")
    print(f"###### Script logger propagate: {script_logger.propagate} ######")
    # ---- END DIAGNOSTIC BLOCK (BEFORE) ----
    log_level = logging.DEBUG if verbose else logging.INFO

    # logging.basicConfig(  # This was found to be ineffective as root is already configured
    #     level=log_level, 
    #     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    # )
    # ---- REMOVE "AFTER basicConfig" DIAGNOSTICS ----
    # print(f"###### Root logger level AFTER basicConfig: {logging.getLevelName(logging.getLogger().level)} ######")
    # print(f"###### Root logger handlers AFTER basicConfig: {logging.getLogger().handlers} ######")

    # Explicitly set the root logger's level. 
    # The existing handler (<StreamHandler <stderr> (NOTSET)>) should pick this up.
    logging.getLogger().setLevel(log_level)
    print(f"###### Root logger level AFTER EXPLICIT SET: {logging.getLevelName(logging.getLogger().level)} ######") # New diagnostic

    # If verbose mode is enabled for the script, also make genesis_lib verbose.
    if verbose:
        # Explicitly set the genesis_lib logger's level.
        # The existing handler (<StreamHandler <stderr> (NOTSET)>) should pick this up.
        genesis_lib_logger = logging.getLogger("genesis_lib")
        genesis_lib_logger.setLevel(log_level)
        print(f"###### genesis_lib logger level AFTER EXPLICIT SET: {logging.getLevelName(genesis_lib_logger.level)} ######") # New diagnostic

    agent_display_name = f"SimpleGenesisAgent{f'-{tag}' if tag else ''}"
    logger.info(f"Initializing '{agent_display_name}' (Log Level: {logging.getLevelName(log_level)})...")
    # Initialize the agent
    agent = SimpleGenesisAgent(service_instance_tag=tag) # Pass tag to constructor
    
    try:
        # Give some time for initialization and announcement propagation (e.g., DDS discovery)
        logger.info("Allowing 2 seconds for agent components to initialize and announce themselves...")
        await asyncio.sleep(2)
        
        logger.info(f"Starting '{agent.agent_name}' main loop. It will now listen for messages via the Genesis interface.")
        logger.info("Press Ctrl+C to stop the agent.")
        
        # The MonitoredAgent (base of OpenAIGenesisAgent) should provide self.app (a GenesisApp instance)
        # which has a run() method to start all services, including DDS listeners.
        # This call is typically blocking and will keep the agent alive.
        # if hasattr(agent, 'app') and callable(getattr(agent.app, 'run', None)):
        #     await agent.app.run()
        # else:
        #     logger.error(f"Could not start '{agent.agent_name}' main loop: 'agent.app.run()' method not found or not callable.")
        #     logger.info("The agent will not be able to receive messages from the Genesis interface.")
            # If app.run() is not available or not blocking, the script might exit or not function as intended.
            # For a robust agent, ensure the underlying GenesisApp framework correctly provides this.

        # GenesisAgent (base class of MonitoredAgent) provides the run() method
        if hasattr(agent, 'run') and callable(getattr(agent, 'run', None)):
            await agent.run() # Corrected: Call agent.run() instead of agent.app.run()
        else:
            logger.error(f"Could not start '{agent.agent_name}' main loop: 'agent.run()' method not found or not callable.")
            logger.info("The agent will not be able to receive messages from the Genesis interface.")

    except KeyboardInterrupt:
        logger.info(f"'{agent.agent_name}' received KeyboardInterrupt. Initiating shutdown...")
    except Exception as e:
        logger.error(f"An unexpected error occurred in '{agent.agent_name}' main loop: {e}", exc_info=True)
    finally:
        logger.info(f"Closing '{agent.agent_name}' and releasing resources...")
        if 'agent' in locals() and agent: # Ensure agent was successfully initialized
            await agent.close()
        logger.info(f"'{agent.agent_name}' has been shut down.")

if __name__ == "__main__":
    # Run the async main function
    # asyncio.run(main()) # Old way

    parser = argparse.ArgumentParser(description="Run the SimpleGenesisAgent.")
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="An optional instance tag to make the agent's RPC service name unique (e.g., 'instance1')."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level) for the agent script and Genesis libraries."
    )
    args = parser.parse_args()

    asyncio.run(main(tag=args.tag, verbose=args.verbose)) # Pass verbose flag to main
