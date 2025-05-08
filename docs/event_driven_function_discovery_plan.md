# Plan for Event-Driven Function Discovery

## Core Principles

### Centralized Discovery Cache
- FunctionRegistry (owned by GenesisApp) will be the single source of truth for discovered functions available on the network
- Its FunctionCapabilityListener will continuously update this cache in real-time as DDS FunctionCapability messages arrive or are disposed

### Event-Driven Updates
- Agents will no longer actively "discover" functions on demand
- Instead, they will access the always-up-to-date cache from GenesisApp/FunctionRegistry

### Simplified Agent Logic
- Agents (especially OpenAIGenesisAgent) will be consumers of this information, simplifying their internal logic

### Robustness & Durability
- This approach naturally supports durability
- If an agent starts before a service, the FunctionRegistry will automatically pick up the service's functions when they are eventually advertised

## Detailed Changes

### FunctionRegistry (genesis_lib/function_discovery.py) Enhancements

#### Responsibility
- Solidify its role as the primary manager of discovered function data received via DDS

#### FunctionCapabilityListener.on_data_available
- Ensure it robustly updates self.registry.discovered_functions not only for new/updated functions but also correctly handles function removal when a FunctionCapability instance is disposed (e.g., info.state.instance_state != dds.InstanceState.ALIVE)
- The listener should directly populate a structured cache (e.g., self.registry.discovered_functions) with all relevant details from the FunctionCapability message

#### Access to Discovered Functions
- Provide a clear, thread-safe public method, e.g., get_all_discovered_functions() -> Dict[str, Dict], which returns a copy or a well-structured view of the current discovered_functions cache
- This dictionary would map function_id to its details
- Consider methods like get_discovered_function_by_name(name: str) for convenience

#### Event Notification (Advanced - Optional for a first pass)
- Could implement an asyncio.Event or a callback system within FunctionRegistry that GenesisApp can expose
- This would allow agents to be notified proactively when the set of available functions changes, rather than polling
- For now, on-demand access by the agent should be sufficient

### GenesisApp (genesis_lib/genesis_app.py) Modifications

#### Responsibility
- Act as the gateway for agents to access discovered function information from its FunctionRegistry instance

#### Expose Function Access
- Add a method like get_available_functions() -> Dict[str, Dict] that simply calls self.function_registry.get_all_discovered_functions()
- This keeps a clean API for the agent and decouples it from the direct FunctionRegistry internals if they were to change

#### No Active Discovery
- GenesisApp itself doesn't initiate discovery; it relies on its FunctionRegistry's passive, event-driven nature

### GenesisAgent (genesis_lib/agent.py) Refactoring

#### Remove Active Discovery
- The existing async def discover_functions(self, function_client, ...) method should be removed or its purpose fundamentally changed
- Agents will no longer call it to find functions

#### Accessing Functions
- When an agent needs to know about available functions (e.g., to prepare a list for an LLM or to decide if it can handle a request), it will call self.app.get_available_functions()

#### Internal State
- Agents that maintain their own specific list or cache of functions (like OpenAIGenesisAgent.function_cache) will populate it by calling self.app.get_available_functions()

### OpenAIGenesisAgent (genesis_lib/openai_genesis_agent.py) Simplification

#### Remove Custom Discovery
- Delete the async def _ensure_functions_discovered(self) method entirely

#### Update Function Usage
- In methods like process_request or process_message, and especially in _get_function_schemas_for_openai, it will now call self.app.get_available_functions() to get the current list of all discovered functions on the network
- It will then filter/transform this list as needed for its self.function_cache and for providing schemas to the OpenAI API
- The logic for deciding self.system_prompt (function-based vs. general) will also rely on the output of self.app.get_available_functions()

### Role of GenericFunctionClient (genesis_lib/generic_function_client.py)
- Its discover_functions method, which actively reads/takes from the FunctionCapability topic, will no longer be the primary mechanism used by agents for continuous discovery
- It might still have utility for specific components that need a one-off, non-continuous query of available functions, but agents will rely on the GenesisApp's cached view

## Benefits of this Plan

### Truly Event-Driven
- Aligns with DDS principles
- Functions appear and disappear in the agent's awareness dynamically

### Reduced Complexity in Agents
- OpenAIGenesisAgent becomes much simpler regarding discovery

### Centralized Logic
- Discovery logic is concentrated in FunctionRegistry and its listener

### Improved Robustness
- Less prone to timing issues (e.g., service starting after agent)

### Testability
- Easier to test components in isolation

### Closer to Base Classes
- The core discovery mechanism (listening and caching) is handled by FunctionRegistry, which is a fundamental part of GenesisApp
- Agents simply consume this information

This approach directly uses the DDS queue's event-driven nature (via the DataReader and its listener in FunctionRegistry) to maintain an up-to-date, in-memory cache of functions, which is then exposed to agents. This seems more efficient and cleaner than agents trying to interact with DDS queues directly for this purpose. 