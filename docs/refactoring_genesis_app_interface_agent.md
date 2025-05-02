# Refactoring Plan: GenesisApp, Interface, and Agent Separation

## 1. Motivation and Reasoning

Currently, the `GenesisApp` class (`genesis_lib/genesis_app.py`) serves as a foundational DDS setup class for both `GenesisInterface` and various Genesis Agents. While aiming for code reuse, this approach has led to several challenges:

1.  **Mixed Concerns:** `GenesisApp` contains components and logic specific to the *Agent* role (e.g., `registration_writer`, `announce_self` method) which are unnecessary and potentially confusing for Interfaces.
2.  **Redundancy:** `GenesisInterface` needs its own `DataReader` with an event-driven listener (`RegistrationListener`) to discover agents effectively. However, `GenesisApp` also creates a separate `DataReader` for the same registration topic, which it uses internally for polling-based self-verification (`take()`) within `announce_self`. This leads to two readers for the same topic within an interface instance.
3.  **Polling vs. Event-Driven:** DDS applications generally benefit from event-driven architectures using listeners (like `on_data_available`) for receiving data asynchronously. This is more efficient and robust than polling loops (`take()` or `read()` in a loop). While `announce_self` uses polling for a specific verification task, the primary mechanism for inter-component communication (like agent discovery) should rely on listeners. The current structure slightly obscures this distinction.
4.  **Role Clarity:** Interfaces and Agents have distinct communication patterns as outlined in `docs/function_call_flow.md`:
    *   **Interfaces:** Primarily clients (Requesters), discovering services.
    *   **Agents:** Primarily servers (Repliers), but also clients (Requesters) and service announcers (DataWriters).
    The shared `GenesisApp` base doesn't fully reflect these distinct roles.

This refactoring aims to address these points by clearly separating the responsibilities into distinct classes, leading to cleaner, more maintainable, and role-appropriate code.

## 2. Goals

*   **Minimal `GenesisApp`:** Refactor `GenesisApp` to contain only the truly shared, minimal DDS infrastructure required by *any* Genesis participant (Interface or Agent).
*   **Clear Role Separation:** Establish distinct base classes (`GenesisInterface`, `GenesisAgent`) that build upon the minimal `GenesisApp` but contain the logic specific to their respective roles.
*   **Promote Listener Usage:** Emphasize and facilitate the use of asynchronous, event-driven DDS listeners (`on_data_available`, `on_subscription_matched`, etc.) for receiving data, especially for discovery mechanisms in the `GenesisInterface`. Polling should be minimized and restricted to specific use cases where necessary (like potential self-verification within the agent's `announce_self`).
*   **Reduce Redundancy:** Eliminate unnecessary DDS entities created by the base class that are not used or are duplicated by derived classes (e.g., the polling `registration_reader` in `GenesisApp` when used by an Interface).
*   **Improve Maintainability:** Make the codebase easier to understand, modify, and extend by aligning class structure with component roles.

## 3. Detailed Refactoring Steps

**Note on Process & Resource Usage:** This refactoring is being done incrementally. Each small change should ideally be followed by running the test suite (`run_scripts/run_all_tests.sh`). Be mindful that complex operations or large changes might hit resource limits (e.g., memory), reinforcing the need for small, verifiable steps.

### Step 3.1: Modify `GenesisApp` (`genesis_lib/genesis_app.py`) - ✅ COMPLETE

**Status:** Completed.

**Action:** Strip `GenesisApp` down to the essential, shared DDS components.

*   **Removed:**
    *   `self.registration_writer` creation and associated `close()` logic.
    *   `self.registration_reader` creation.
    *   `announce_self()` method definition.
*   **Kept:**
    *   Initialization of `participant`, `agent_id`, `preferred_name`, `dds_guid`.
    *   `type_provider` and `registration_type` definition.
    *   `registration_topic` definition.
    *   Base `publisher` and `subscriber` creation.
    *   `function_registry` and related discovery logic.
    *   Updated `close()` method (only closes remaining entities: `participant`, `publisher`, `subscriber`, `function_registry`).

**Observations during completion:**
*   Removing `self.registration_reader` initially did *not* cause test failures. The `try/except Exception` block in the original `announce_self` method silently caught the `AttributeError` when `self.registration_reader.take()` was called for self-verification, allowing the announcement publication (`registration_writer.write()`) to proceed.
*   Removing `announce_self` subsequently also did *not* cause test failures in `run_all_tests.sh`. Investigation revealed that the key test involving an agent (`run_test_agent_with_functions.sh` executing `test_agent.py`) initializes an `OpenAIGenesisAgent` but **does not call the standard `agent.run()` method**. Instead, it calls `agent.process_message()` directly. Since `agent.run()` is where the (now removed) `self.app.announce_self()` was called, this specific test was unaffected.
*   **Implication:** The current test suite doesn't fully cover the standard agent lifecycle startup, specifically the announcement part triggered by `agent.run()`. This is something to address later (perhaps in Step 3.5).

### Step 3.2: Create/Modify `GenesisAgent` Base Class (e.g., `genesis_lib/agent.py`) - ⏳ IN PROGRESS

**Action:** Create a base class for Agents that inherits from or composes `GenesisApp` and adds Agent-specific logic.

**Next Immediate Action:**
1.  Add the `registration_writer` creation logic back into `GenesisAgent.__init__`, using `self.app.publisher` and `self.app.registration_topic`. Define appropriate QoS (TRANSIENT_LOCAL durability, reliable, etc.).
2.  Update the `GenesisAgent.close()` method to include closing this newly added `self.registration_writer`.
3.  Run tests to ensure this addition doesn't break anything unexpectedly.

**Subsequent Actions for this Step:**
*   **Inheritance/Composition:** Confirm composition (`self.app = GenesisApp(...)`) is the desired approach (already implemented).
*   **Add Agent Logic:**
    *   Move (re-implement) the `announce_self()` method logic here.
    *   **Self-Verification (Optional Polling):** If `announce_self` still requires polling-based verification:
        *   Create the necessary `registration_reader` *within* the `GenesisAgent` class (perhaps locally within `announce_self`). Use `take()` for verification. This reader is now clearly Agent-specific.
    *   **Replier Setup:** Verify the existing `Replier` setup in `GenesisAgent` is sufficient.
    *   Update the `close()` method to handle all agent-specific resources (`registration_writer`, `Replier`).

### Step 3.3: Modify `GenesisInterface` (`genesis_lib/interface.py`) - 📋 TO DO

**Action:** Ensure `GenesisInterface` correctly uses the refactored `GenesisApp` and retains its Interface-specific logic.

*   **Adapt to `GenesisApp`:** Update the initialization (`__init__`) to work with the slimmer `GenesisApp`. It will still use `self.app` (composition).
*   **Verify `Requester`:** Ensure the `rpc.Requester` is still created correctly using the `participant` from `self.app`.
*   **Verify Registration Monitoring:** Confirm that `_setup_registration_monitoring` correctly creates the `registration_reader` using the `subscriber` and `registration_topic` from `self.app`.
*   **Confirm Listener Usage:** Double-check that this reader is correctly configured with the `RegistrationListener` and uses `on_data_available` and `on_subscription_matched` for event-driven discovery. This part should already be correct based on our previous work but needs verification after the `GenesisApp` changes.
*   Update the `close()` method if needed (though it primarily delegates to `self.app.close()` and closes its `requester`).

### Step 3.4: Update Agent Implementations - 📋 TO DO

**Action:** Modify specific agent implementations (like `MathTestAgent`) to inherit from/use the new `GenesisAgent` base class instead of directly using or replicating `GenesisApp` logic.

*   Change inheritance or instantiation as needed.
*   Ensure they correctly implement any abstract methods from `GenesisAgent` (e.g., for setting up the Replier).
*   Remove any redundant DDS setup code now handled by `GenesisAgent` or `GenesisApp`.

### Step 3.5: Update Test Scripts and Examples - 📋 TO DO

**Action:** Modify test scripts and examples (`run_scripts/math_test_agent.py`, `run_scripts/math_test_interface.py`, `run_scripts/run_math_interface_agent_simple.sh`, etc.) to reflect the new class structure.

*   Ensure agents and interfaces are instantiated correctly using their respective classes.
*   Adjust any direct calls or assumptions based on the old `GenesisApp` structure.
*   Consider adding a test that specifically exercises the `agent.run()` method to verify the announcement mechanism once it's moved to `GenesisAgent`.

## 4. Testing Strategy

*   **Existing Tests:** Run the `run_math_interface_agent_simple.sh` test script frequently throughout the refactoring process to ensure the core functionality (agent announcement, interface discovery, RPC call) remains intact.
*   **Unit Tests:** Consider adding unit tests for:
    *   `GenesisApp`: Verifying correct initialization of minimal DDS components.
    *   `GenesisAgent`: Verifying `registration_writer` creation and `announce_self` functionality.
    *   `GenesisInterface`: Verifying `Requester` creation and `registration_reader`/`listener` setup.
*   **Monitor Logs:** Pay close attention to logs during testing to ensure:
    *   Agents correctly publish announcements.
    *   Interfaces correctly discover agents using the listener (and not via RPC discovery first, ideally).
    *   RPC calls succeed.
    *   No errors related to missing or incorrect DDS entities occur.
    *   Cleanup (`close()`) happens without errors.
    *   Agent announcement errors (once `announce_self` is moved).

## 5. Conclusion

This refactoring will result in a more robust, maintainable, and logically structured Genesis library. By clearly separating the roles of the core application, interfaces, and agents, and by prioritizing event-driven DDS patterns, the system will be easier to understand, extend, and debug. 