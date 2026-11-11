# The two T4 smoke runs before the H100 replay (November 10, 2026)

`cloud/replay_app.py::smoke`: Qwen3-1.7B on one T4, three sessions of the corpus, each arm
once. They check the plumbing on a real vLLM: every unit of both runs is exact. Their
times say nothing about the H100.

- `20261110-031029-smoke`: do not read its `wide` and `nospec-wide` rows. The replay
  client pooled 256 keep-alive connections there, where rlms' own client pools 100, and
  httpx's async pool fell to a third of its rate at 128 in flight. The other four arms
  are not affected.
- `20261110-040955-smoke` has the fix (the client is built as rlms builds its own):
  seconds after the streams 89 (`nospec`), 41 (`nospec-wide`), 4 (`wide`), 1
  (`wide-threads`).
