# Replay corpus (built from recorded `nospec` sessions)

Each session was run again offline while it was built: every block printed what it printed in the recorded run, and every turn's message history has the recorded sha256.

| session | from | turns | root tokens | recorded stream s | recorded after-stream s | sub-calls answered | returned an error | batches / single calls | sub-call output tokens | ends with |
|---|---|---|---|---|---|---|---|---|---|---|
| trec132k-17000232.fix1 | 20261110-173155-record nospec_c8_r1 | 9 | 2196 | 123.0 | 0.5 | 13 | 0 | 1 / 0 | 69 | answer |
| trec132k-17000241.fix1 | 20261110-173155-record nospec_c8_r1 | 12 | 2335 | 129.5 | 0.0 | 0 | 0 | 0 / 0 | 0 | default_answer |
| trec132k-17000222.fix1 | 20261110-173155-record nospec_c8_r1 | not replayable: turn 6: the recorded reply was cut; turn 7: the recorded reply was cut; turn 8: the recorded reply was cut; turn 9: the  | | | | | | | | |
| trec132k-17000237.fix1 | 20261110-173155-record nospec_c8_r1 | 8 | 1840 | 94.6 | 440.6 | 6362 | 0 | 320 / 0 | 74781 | answer |
| pairs32k-16.fix1 | 20261110-173155-record nospec_c8_r1 | 12 | 3182 | 168.8 | 8.4 | 40 | 0 | 1 / 0 | 2346 | answer |
| pairs32k-20.fix1 | 20261110-173155-record nospec_c8_r1 | not replayable: turn 11: the recorded reply was cut; turn 12: the recorded reply was cut | | | | | | | | |
| pairs32k-1.fix1 | 20261110-173155-record nospec_c8_r1 | 7 | 1580 | 82.5 | 38.7 | 787 | 0 | 40 / 0 | 3953 | answer |
| pairs32k-15.fix1 | 20261110-173155-record nospec_c8_r1 | 12 | 5087 | 262.9 | 0.0 | 0 | 0 | 0 / 0 | 0 | answer |
| trec132k-17000232.fix2 | 20261110-173155-record nospec_c8_r2 | not replayable: turn 4: the recorded reply was cut; turn 5: the recorded reply was cut; turn 6: the recorded reply was cut; turn 7: the  | | | | | | | | |
| trec132k-17000241.fix2 | 20261110-173155-record nospec_c8_r2 | 12 | 2326 | 104.6 | 5.0 | 4 | 0 | 0 / 4 | 9 | default_answer |
| trec132k-17000222.fix2 | 20261110-173155-record nospec_c8_r2 | 10 | 2268 | 104.3 | 699.7 | 4 | 1 | 0 / 5 | 16384 | deadline |
| trec132k-17000237.fix2 | 20261110-173155-record nospec_c8_r2 | 12 | 3385 | 151.6 | 76.6 | 3205 | 1 | 161 / 1 | 9819 | answer |
| pairs32k-16.fix2 | 20261110-173155-record nospec_c8_r2 | 10 | 1981 | 88.9 | 25.6 | 1574 | 0 | 2 / 0 | 4701 | answer |
| pairs32k-20.fix2 | 20261110-173155-record nospec_c8_r2 | not replayable: turn 8 block 1: output differs from the recorded one; turn 9: message history differs from the recorded one; turn 10: me | | | | | | | | |
| pairs32k-1.fix2 | 20261110-173155-record nospec_c8_r2 | 7 | 1502 | 72.6 | 17.8 | 786 | 0 | 40 / 0 | 2350 | answer |
| pairs32k-15.fix2 | 20261110-173155-record nospec_c8_r2 | not replayable: turn 6 block 1: output differs from the recorded one; turn 7: message history differs from the recorded one; turn 7 bloc | | | | | | | | |

Output tokens of batch elements are counted with the model's tokenizer. On the 13 recorded single calls, where the exact count is known, the count is exact for 6 (mean difference 0.538, largest 1).
