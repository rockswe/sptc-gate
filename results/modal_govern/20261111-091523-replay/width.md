# What width bought, and where the client was the limit (measured)

## Bursts

A burst: sub-calls of one session sent less than 3 s apart. In flight: sent and not yet back, by the client's clock. Whole process: the sub-calls of every session while the burst ran. Engine: its own count of requests, roots included (`/metrics`, two samples a second).

| unit | session | calls | tokens written, median | sent at s | lasted s | calls a second | in flight, mean / most | 100 in flight after s | sub-call ms, median / 90th | whole process: in flight, mean / most | whole process: calls a second | engine: running, median / most; waiting, most |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | pairs32k-1.fix1 | 787 | 5 | 31.8 | 15.1 | 52 | 16 / 16 | - | 289 / 379 | 16 / 32 | 52 | 19 / 36; 0 |
| stream_c8_r1 | trec132k-17000237.fix1 | 3,181 | 20 | 46.2 | 211.4 | 15 | 16 / 16 | - | 1,006 / 1,377 | 24 / 50 | 39 | 22 / 43; 4 |
| stream_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 132.2 | 11.8 | 67 | 15 / 16 | - | 221 / 324 | 33 / 34 | 81 | 31 / 33; 0 |
| stream_c8_r1 | pairs32k-1.fix2 | 786 | 3 | 146.3 | 12.1 | 65 | 15 / 16 | - | 224 / 328 | 39 / 50 | 106 | 32 / 43; 0 |
| stream_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 153.4 | 12.1 | 65 | 15 / 16 | - | 222 / 330 | 39 / 50 | 107 | 31 / 43; 0 |
| stream_c8_r1 | trec132k-17000237.fix2 | 3,185 | 2 | 194.8 | 78.7 | 40 | 9 / 16 | - | 205 / 325 | 24 / 34 | 52 | 22 / 36; 16 |
| stream_c8_r1 | trec132k-17000237.fix1 | 3,181 | 3 | 283.3 | 46.6 | 68 | 16 / 16 | - | 207 / 322 | 17 / 17 | 68 | 11 / 19; 0 |
| wide_c8_r1 | pairs32k-1.fix1 | 787 | 5 | 32.4 | 4.2 | 185 | 86 / 120 | 0.15 | 447 / 600 | 86 / 120 | 185 | 40 / 73; 0 |
| wide_c8_r1 | trec132k-17000237.fix1 | 3,181 | 20 | 47.3 | 54.8 | 58 | 71 / 120 | 0.15 | 1,103 / 1,805 | 73 / 122 | 58 | 64 / 119; 40 |
| wide_c8_r1 | trec132k-17000237.fix1 | 3,181 | 3 | 127.1 | 18.6 | 171 | 90 / 120 | 0.20 | 446 / 897 | 134 / 250 | 213 | 36 / 141; 0 |
| wide_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 136.4 | 6.5 | 122 | 120 / 128 | 0.05 | 974 / 1,355 | 210 / 250 | 212 | 31 / 141; 0 |
| wide_c8_r1 | pairs32k-1.fix2 | 786 | 3 | 150.4 | 6.0 | 131 | 88 / 120 | 0.35 | 570 / 1,232 | 159 / 250 | 175 | 24 / 134; 0 |
| wide_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 153.2 | 5.3 | 148 | 121 / 128 | 0.05 | 876 / 1,498 | 175 / 250 | 208 | 13 / 134; 0 |
| wide_c8_r1 | trec132k-17000237.fix2 | 3,185 | 2 | 195.5 | 57.5 | 55 | 14 / 20 | - | 234 / 356 | 16 / 22 | 55 | 8 / 24; 0 |
| auto_c8_r1 | pairs32k-1.fix1 | 787 | 5 | 32.1 | 4.7 | 169 | 133 / 250 | 1.25 | 798 / 1,061 | 133 / 250 | 169 | 45 / 156; 0 |
| auto_c8_r1 | trec132k-17000237.fix1 | 3,181 | 20 | 47.5 | 33.0 | 96 | 125 / 241 | 1.30 | 1,179 / 2,032 | 125 / 241 | 96 | 120 / 236; 40 |
| auto_c8_r1 | trec132k-17000237.fix1 | 3,181 | 3 | 105.3 | 14.0 | 227 | 184 / 251 | 1.30 | 769 / 1,212 | 187 / 254 | 227 | 35 / 116; 0 |
| auto_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 137.3 | 3.8 | 206 | 132 / 242 | 1.35 | 635 / 937 | 135 / 245 | 206 | 48 / 86; 0 |
| auto_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 150.9 | 8.7 | 90 | 169 / 256 | 1.40 | 1,652 / 3,029 | 351 / 515 | 169 | 28 / 150; 0 |
| auto_c8_r1 | pairs32k-1.fix2 | 786 | 3 | 151.0 | 9.0 | 88 | 175 / 256 | 1.30 | 1,830 / 3,840 | 342 / 515 | 175 | 28 / 150; 0 |
| auto_c8_r1 | trec132k-17000237.fix2 | 3,185 | 2 | 196.3 | 57.9 | 55 | 15 / 20 | - | 235 / 356 | 18 / 23 | 55 | 9 / 24; 0 |
| auto-past_c8_r1 | pairs32k-1.fix1 | 787 | 5 | 32.2 | 4.1 | 190 | 136 / 255 | 1.15 | 723 / 971 | 136 / 255 | 190 | 49 / 123; 0 |
| auto-past_c8_r1 | trec132k-17000237.fix1 | 3,181 | 20 | 47.1 | 34.0 | 93 | 125 / 226 | 1.10 | 1,159 / 2,324 | 126 / 226 | 94 | 126 / 220; 40 |
| auto-past_c8_r1 | trec132k-17000237.fix1 | 3,181 | 3 | 106.6 | 14.4 | 221 | 181 / 252 | 1.20 | 806 / 1,192 | 184 / 255 | 221 | 25 / 143; 0 |
| auto-past_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 137.5 | 3.8 | 210 | 136 / 256 | 1.15 | 664 / 927 | 139 / 259 | 210 | 28 / 55; 0 |
| auto-past_c8_r1 | pairs32k-1.fix2 | 786 | 3 | 150.5 | 8.6 | 91 | 161 / 242 | 1.25 | 1,809 / 2,951 | 344 / 487 | 182 | 32 / 96; 0 |
| auto-past_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 150.6 | 8.6 | 92 | 180 / 246 | 1.25 | 2,000 / 2,759 | 346 / 487 | 180 | 35 / 96; 0 |
| auto-past_c8_r1 | trec132k-17000237.fix2 | 3,185 | 2 | 195.8 | 13.6 | 234 | 178 / 240 | 1.20 | 771 / 1,027 | 181 / 243 | 234 | 25 / 103; 0 |
| wide-open_c8_r1 | pairs32k-1.fix1 | 787 | 5 | 32.2 | 4.8 | 163 | 88 / 120 | 0.15 | 533 / 750 | 88 / 120 | 163 | 41 / 107; 0 |
| wide-open_c8_r1 | trec132k-17000237.fix1 | 1,780 | 20 | 47.4 | 34.8 | 51 | 76 / 120 | 0.15 | 1,167 / 2,539 | 79 / 124 | 52 | 66 / 128; 83 |
| wide-open_c8_r1 | trec132k-17000237.fix1 | 1,401 | 20 | 80.4 | 24.3 | 58 | 63 / 120 | 1.75 | 1,064 / 1,411 | 72 / 133 | 62 | 65 / 125; 0 |
| wide-open_c8_r1 | trec132k-17000237.fix1 | 3,181 | 3 | 130.5 | 20.5 | 155 | 94 / 120 | 0.30 | 516 / 1,129 | 144 / 252 | 193 | 32 / 109; 0 |
| wide-open_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 139.9 | 7.7 | 102 | 121 / 128 | 0.05 | 1,314 / 1,490 | 223 / 252 | 192 | 31 / 83; 0 |
| wide-open_c8_r1 | pairs32k-1.fix2 | 786 | 3 | 153.6 | 3.7 | 212 | 87 / 120 | 0.15 | 390 / 544 | 91 / 124 | 212 | 41 / 51; 0 |
| wide-open_c8_r1 | pairs32k-16.fix2 | 787 | 3 | 157.4 | 3.0 | 264 | 114 / 128 | 0.05 | 422 / 629 | 118 / 132 | 264 | 41 / 96; 0 |
| wide-open_c8_r1 | trec132k-17000237.fix2 | 3,185 | 2 | 198.5 | 56.3 | 57 | 14 / 20 | - | 230 / 349 | 18 / 24 | 57 | 10 / 26; 0 |

## Root turns that waited for their first token, and the engine's queue

| unit | root turns | waited 0.5 s or more | session, turn | began at s | TTFT s | long prompts sent in the 3 s before or while it waited: number, tokens | samples with a request waiting | of them within 2.5 s after a long prompt was sent |
|---|---|---|---|---|---|---|---|---|
| stream_c8_r1 | 111 | 0 | - | - | - | - | 10 of 1276 | 10 |
| wide_c8_r1 | 111 | 1 | trec132k-17000237.fix2, 1 | 76.4 | 1.28 | 3, 78,866 | 9 of 1266 | 9 |
| auto_c8_r1 | 111 | 1 | trec132k-17000237.fix2, 1 | 76.2 | 2.73 | 4, 114,996 | 7 of 922 | 7 |
| auto-past_c8_r1 | 111 | 1 | trec132k-17000237.fix2, 1 | 75.9 | 2.80 | 4, 114,988 | 10 of 917 | 10 |
| wide-open_c8_r1 | 111 | 1 | trec132k-17000237.fix2, 1 | 76.1 | 4.39 | 5, 151,208 | 13 of 585 | 9 |

## The governor

| unit | moves | cuts: at s, session, window, engine waiting / running | moves down to a share of the process's ceiling | windows opened: number, from, to, seconds, steps (medians) | client CPU share at its moves, median / most | growth moves at 0.9 of a core or more | engine token pace above quiet at its moves, median / most |
|---|---|---|---|---|---|---|---|
| auto_c8_r1 | 134 | 61.8 trec132k-17000237.fix1 256 to 179 (40 / 151); 61.8 trec132k-17000241.fix2 16 to 11 (40 / 151); 77.2 trec132k-17000222.fix2 16 to 11 (3 / 10); 77.2 trec132k-17000237.fix1 256 to 179 (3 / 10) | 0 | 8 of 3 steps or more: 16 to 256 in 1.51 s, 7 steps | 0.12 / 1.26 | 19 of 50 | 0.02 / 0.19 |
| auto-past_c8_r1 | 149 | 60.7 trec132k-17000237.fix1 256 to 179 (40 / 131); 60.7 trec132k-17000241.fix2 16 to 11 (40 / 131) | 0 | 9 of 3 steps or more: 16 to 256 in 1.51 s, 7 steps | 0.08 / 1.24 | 20 of 56 | 0.03 / 0.64 |
