# Known Issues

## Service Name Propagation Timing Issue

### Description
There is a known timing issue with service name propagation in the function discovery system. The `FunctionCapabilityListener` occasionally reports errors about `NoneType` objects not being subscriptable when processing function capabilities. However, the service name is eventually correctly propagated to the `GenericFunctionClient`, suggesting this is a race condition or timing issue in the discovery process.

### Symptoms
- Error messages in logs: `Error processing function capability: 'NoneType' object is not subscriptable`
- These errors appear multiple times during function discovery
- Despite the errors, the service name is eventually correctly discovered and used by the `GenericFunctionClient`

### Affected Components
- `FunctionCapabilityListener`
- `FunctionRegistry`
- `GenericFunctionClient`

### Workaround
The system continues to function correctly despite these errors, as the service name is eventually properly propagated. However, these errors should be addressed to improve the robustness of the function discovery process.

### Status
- **Priority**: Medium
- **Status**: Known issue, under investigation
- **Impact**: Non-blocking (system continues to function)

## Function Discovery Inheritance Issue

### Description
The function discovery mechanism is currently buried too deep in the inheritance hierarchy, leading to services discovering each other unnecessarily. This architectural issue needs to be addressed by moving the function discovery logic to a higher level in the inheritance chain.

### Symptoms
- Services are discovering other services when they should only be discoverable by clients
- Increased network traffic due to unnecessary discovery messages
- Potential for service-to-service communication when not intended

### Affected Components
- Service inheritance hierarchy
- Function discovery mechanism
- Network communication patterns

### Workaround
Currently, no workaround is implemented. The system continues to function but with suboptimal discovery patterns.

### Status
- **Priority**: High
- **Status**: Known architectural issue, needs refactoring
- **Impact**: Performance and architectural cleanliness 