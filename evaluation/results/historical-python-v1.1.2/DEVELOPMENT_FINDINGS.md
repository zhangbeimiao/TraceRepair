# Development findings: historical-python-v1.1.2

This frozen development attempt ran only the three declared development tasks on the disposable
GitHub Actions runner. The HTTPie and youtube-dl locked tasks were not opened.

PySnooper and TheFuck passed both the target and regression gates. The planner-output normalization
in Agent 0.6.0-dev3 recovered PySnooper's previously unknown plan kind without weakening any tool,
patch, or test policy. tqdm stopped safely during patch generation because its fourth model response
used exactly the 512-token per-call limit and ended as incomplete JSON. No patch was applied or
accepted for that task.

The next development version will make one evidence-backed budget change: increase the per-call
completion ceiling from 512 to 800 tokens while keeping the four-call limit, 2,048-token task budget,
one patch attempt, and all deterministic gates unchanged. It will not add a tqdm-specific patch,
source path, or hidden test value.

- workflow run: `39581026912`
- development result: 2/3 pass@1
- human handoff: 1/3
- incorrect accepted patches: 0
- average completion tokens: 366.67
- P50 / P95 wall time: 9.458s / 17.984s
- terminal ledger hash: `9bee4e272608cdc6dbd7d304f337ad96786ae59c81529dec76ea25de3c9085b5`
- report SHA-256: `37e9b1c87901e435689626cab9bb5aa43a4164863b7e1820ed5dec9841ff287d`
- locked split: not opened

The original ledger and report remain unchanged.
