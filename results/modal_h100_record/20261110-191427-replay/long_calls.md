# Long sub-calls and the sessions next to them (measured)

A long sub-call: a prompt of at least 5,000 tokens. The window runs from the first of them leaving to the last one coming back. Root gaps are those of the other sessions; a stall is a gap far above the usual one (analyze.stalls).

| unit | long calls | sent within s | in flight at once | window s | KV peak in window (unit) | preemptions in window (unit) | waiting max in window (unit) | other roots in window: gap p50 / p99 / max ms, stall s | outside it |
|---|---|---|---|---|---|---|---|---|---|
| stream-open_c8_r1 | 4 | 0.0 | 4 | 183 | 0.88 (0.88) | 0 (0) | 17 (17) | 42.7 / 61.4 / 444, 3.5 s | 43.7 / 61.2 / 441, 23.4 s |
| stream_c8_r1 | 0 | - | - | - | - (0.37) | - (0) | - (5) | - | 43.6 / 57.8 / 441, 23.5 s |
| nospec_c8_r1 | 0 | - | - | - | - (0.34) | - (0) | - (4) | - | 43.2 / 56.6 / 443, 16.7 s |
| wide_c8_r1 | 0 | - | - | - | - (0.40) | - (0) | - (40) | - | 43.0 / 68.8 / 3462, 52.2 s |

## stream-open_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 183.1 | 36,103 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 183.4 | 36,126 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 183.2 | 36,211 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 183.4 | 6,021 | 4,096 | yes |
