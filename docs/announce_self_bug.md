# Bug Report: announce_self AttributeError in MonitoredAgent Inheritance

**Date:** 2025-05-02

**Status:** Unresolved

## Summary

Agents inheriting from `MonitoredAgent` (which inherits from `GenesisAgent`) are currently failing to announce their presence via the `GenesisRegistration` DDS topic. This is due to an unexpected `AttributeError` occurring when the `GenesisAgent.run()` method attempts to call `self.announce_self()`.

## Steps to Reproduce

1.  Ensure the workspace is clean (no lingering test processes or `rtiddsspy` instances).
2.  Run the simple math interface/agent test script from the workspace root:
    ```bash
    bash run_scripts/run_math_interface_agent_simple.sh
    ```

## Expected Behavior

*   The script should complete successfully (exit code 0).
*   The agent (`math_test_agent.py`) should successfully call `announce_self` and publish its registration data.
*   The interface (`math_test_interface.py`) should detect the agent via the registration announcement and proceed with the RPC call.
*   The `rtiddsspy_math.log` should show `New data` for the `GenesisRegistration` topic.
*   The script's final check for the registration announcement should pass.

## Actual Behavior

*   The script fails with exit code 1, showing `❌ TRACE: Interface failed`.
*   The agent log (`logs/math_test_agent.log`) shows a fatal error:
    ```
    AttributeError: 'MathTestAgent' object has no attribute 'announce_self'
    ```
    This occurs when `GenesisAgent.run()` calls `await self.announce_self()`.
*   The interface log (`logs/math_test_interface.log`) shows a timeout error:
    ```
    ERROR - Timeout waiting for registration subscription to be matched
    ERROR - ❌ TRACE: No agent found, exiting
    ```
*   The DDS Spy log (`logs/rtiddsspy_math.log`) shows no `New data` samples for the `GenesisRegistration` topic, confirming the announcement was never published.

## Analysis

The `AttributeError` is puzzling because:
*   `announce_self` is clearly defined as an instance method in the base class `GenesisAgent`.
*   `MonitoredAgent` inherits from `GenesisAgent`.
*   `MathTestAgent` inherits from `MonitoredAgent`.
*   Neither `MonitoredAgent` nor `MathTestAgent` override `announce_self` or `run`.
*   Standard Python inheritance and Method Resolution Order (MRO) suggest that `self.announce_self()` called within `GenesisAgent.run` on a `MathTestAgent` instance should find the method in `GenesisAgent`.

Attempts to resolve this (clearing `.pyc` cache, explicitly calling `super()` in `MonitoredAgent`) have failed, suggesting a potential deeper issue related to the runtime environment, imports, or class loading specific to this inheritance chain (`MathTestAgent` -> `MonitoredAgent` -> `GenesisAgent`).

## Next Steps

*   Temporarily skip fixing this bug and proceed with refactoring Step 3.3 (`GenesisInterface`) to see if subsequent changes alter the behavior.
*   Revisit this issue after other refactoring steps are complete.
*   Investigate potential environment issues or complex import interactions if the problem persists. 