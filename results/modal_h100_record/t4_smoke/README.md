# The T4 smoke run before the H100 recording (November 10, 2026)

`cloud/record_app.py::smoke`: Qwen3-1.7B on one T4, two TREC tasks, one `nospec` unit with
rlms' batch path fixed. It checks the plumbing of `cloud/rlm_record.py` on a real vLLM.
5 minutes.

- The probe is what it was for. Four batches of 20 prompts through rlms' own path, the
  last after 6 s without a request: stock rlms 0.1.3 lost 21 of 80 (0, 16, 4 and 1 by
  batch), the fixed path none (`campaign.jsonl`, `batch_probe`).
- Its unit made no batched call. A model that small writes none: both sessions ran 12
  turns of root text, each reply cut after 300 deltas on purpose. `batch_fix.json` says 0
  prompts went through the fix.
- Its times say nothing about the H100.
