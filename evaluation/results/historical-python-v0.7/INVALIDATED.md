# historical-python-v0.7 invalidation record

This benchmark was preserved but excluded from repair-quality claims because the
operator accidentally configured `DASHSCOPE_API_KEY` with a one-character value.
Both development tasks received HTTP 400 before any model completion or tool call.
The locked task was not attempted.

The original evidence was not deleted or rewritten:

- terminal ledger hash: `1003a59dd65f70a09c12874e2167bbd6afeed3be1db7c94b829a1e10d16a3662`
- report SHA-256: `0bcdf185cd5ab911098dfc0e7f73ecd1b842238c2a27b4f02f1af8ed3cd3b228`
- observed outcomes: 0/2, both provider failures before model/tool execution

After a separate smoke request succeeded with a correctly configured workspace
credential, evaluation moved to `historical-python-v0.7.1`. This is an explicit
infrastructure-invalidated run, not a retry silently substituted into v0.7.
