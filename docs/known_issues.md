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

## NLP Communication Topic Size Limitation

### Description
The natural language processing communication topics (InterfaceAgentRequest, InterfaceAgentReply, AgentAgentRequest, and AgentAgentReply) are currently bounded at 8K characters. This limitation may be insufficient for complex NLP interactions and needs to be addressed by either implementing proper streaming support or using unbounded strings.

### Symptoms
- Messages exceeding 8K characters may be truncated
- Potential loss of information in complex NLP interactions
- System may not handle large language model responses effectively

### Affected Components
- InterfaceAgentRequest/Reply
- AgentAgentRequest/Reply
- Any components using these communication channels

### Workaround
Currently, messages need to be kept under 8K characters. For larger messages, they may need to be split into multiple smaller messages.

### Status
- **Priority**: High
- **Status**: Known issue, needs implementation
- **Impact**: May affect quality and completeness of NLP interactions 