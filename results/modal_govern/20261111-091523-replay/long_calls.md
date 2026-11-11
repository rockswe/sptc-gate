# Long sub-calls and the sessions next to them (measured)

A long sub-call: a prompt of at least 5,000 tokens. The window runs from the first of them leaving to the last one coming back. Root gaps are those of the other sessions; a stall is a gap far above the usual one (analyze.stalls).

| unit | long calls | sent within s | in flight at once | window s | KV peak in window (unit) | preemptions in window (unit) | waiting max in window (unit) | other roots in window: gap p50 / p99 / max ms, stall s | outside it |
|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 4 | 368.4 | 2 | 539 | 0.45 (0.45) | 0 (0) | 16 (16) | 45.5 / 55.9 / 442, 8.2 s | 42.8 / 55.4 / 445, 20.4 s |
| wide_c8_r1 | 4 | 358.0 | 2 | 530 | 0.48 (0.48) | 0 (0) | 21 (40) | 44.3 / 70.7 / 444, 7.4 s | 44.5 / 110.7 / 489, 20.6 s |
| auto_c8_r1 | 4 | 187.1 | 3 | 358 | 0.74 (0.74) | 0 (0) | 3 (40) | 44.1 / 80.3 / 445, 18.6 s | 44.4 / 126.4 / 444, 21.7 s |
| auto-past_c8_r1 | 4 | 184.3 | 3 | 357 | 0.73 (0.73) | 0 (0) | 3 (40) | 44.2 / 79.8 / 445, 17.5 s | 44.1 / 121.8 / 447, 21.9 s |
| wide-open_c8_r1 | 4 | 0.0 | 4 | 189 | 0.96 (0.96) | 0 (0) | 83 (83) | 44.6 / 83.0 / 456, 18.8 s | 44.1 / 121.5 / 446, 21.6 s |

## stream_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 190.3 | 36,103 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 190.3 | 6,021 | 4,096 | yes |
| trec132k-17000222.fix2 | 190.3 | 178.2 | 36,211 | 4,096 | yes |
| trec132k-17000222.fix2 | 368.4 | 170.7 | 36,126 | 4,096 | yes |

## wide_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 186.7 | 36,103 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 186.7 | 6,021 | 4,096 | yes |
| trec132k-17000222.fix2 | 186.7 | 171.4 | 36,211 | 4,096 | yes |
| trec132k-17000222.fix2 | 358.0 | 172.4 | 36,126 | 4,096 | yes |

## auto_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 187.1 | 36,104 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 187.4 | 36,127 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.2 | 187.4 | 6,022 | 4,096 | yes |
| trec132k-17000222.fix2 | 187.1 | 170.5 | 36,212 | 4,096 | yes |

## auto-past_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 184.3 | 36,102 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 184.3 | 6,020 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.3 | 184.5 | 36,125 | 4,096 | yes |
| trec132k-17000222.fix2 | 184.3 | 172.2 | 36,210 | 4,096 | yes |

## wide-open_c8_r1: the long calls

| session | sent at s | took s | prompt tokens | output tokens | speculative |
|---|---|---|---|---|---|
| trec132k-17000222.fix2 | 0.0 | 188.7 | 36,104 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 188.8 | 36,127 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 189.1 | 36,212 | 4,096 | yes |
| trec132k-17000222.fix2 | 0.0 | 189.1 | 6,022 | 4,096 | yes |
