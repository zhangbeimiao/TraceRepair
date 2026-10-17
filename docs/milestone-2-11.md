# Milestone 2-11: LangGraph diagnostic state graph

## Why add LangGraph before an LLM

TraceRepair now uses a real `StateGraph`, but its routing is still deterministic.
This separates two concerns: graph execution owns legal node transitions, while
model planning will later decide which allowed tool action to request. It avoids
making a first model integration responsible for persistence, routing, and
failure handling all at once.

## Graph shape

`START -> diagnose -> diagnose | END`

Each `diagnose` node asks the existing deterministic controller for exactly one
legal next action. The durable trace controls whether that action is repository
mapping, code search, file read, or target-test execution. When the controller
hands the task to a human, the graph reaches `END`.

## Durability boundary

`TraceStore` remains the only durable task store. Every tool call persists a
checkpoint, and a rebuilt graph routes from those completed-tool records. This
means an interrupted process can construct a new graph using the same task id
without replaying already completed tools. LangGraph's in-memory checkpointer is
intentionally not used here because it would not survive a process restart.

The graph also writes a compact `graph_node_completed` trace event after every
node, so graph-level routing and tool-level execution can be inspected together.
