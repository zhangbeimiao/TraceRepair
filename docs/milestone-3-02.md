# Milestone 3.02: bounded development-set benchmark

TraceRepair now has a bounded repeat benchmark for development cases 01, 03, 07, and 10.

The benchmark adds one run per case by default and never accepts more than two repeats. Each
agent run remains limited to four provider requests, so the default command has a hard ceiling
of sixteen requests.

A development-set baseline is frozen only when:

- every case has at least two runs for the same agent version;
- every case has at least a 50% success rate;
- the combined success rate is at least 80%.

The frozen manifest contains only trace-derived metrics and identifiers. It does not include API
keys, model response bodies, source code, or patches.
