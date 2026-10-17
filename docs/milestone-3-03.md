# Milestone 3.03: locked evaluation and trace showcase

The frozen `0.4.0-dev1` agent can now be evaluated once against locked cases 02, 04, 06, 08,
and 09. The runner refuses a different agent version, never repeats an existing case, and only
resumes cases that have no recorded run. Successful and failed outcomes are both preserved.

The locked manifest is written only when every case has exactly one finished run. It records
trace-derived metrics, not prompts, model response bodies, source code, patches, test output, or
credentials.

`scripts/show_trace_demo.py` renders a real repair trace as a presentation-safe execution
timeline. It demonstrates state transitions, bounded model decisions, tool calls, policy checks,
and verification gates without exposing raw artifacts.
