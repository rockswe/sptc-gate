| pattern | baseline meas (s) | baseline sim | spec meas (s) [min-max of 5] | spec sim (LOO) | err | in range | speedup meas | speedup sim |
|---|---|---|---|---|---|---|---|---|
| batched8 | 1.12 | 1.13 | 1.00 [1.00-1.00] | 1.00 | +0.0% | yes | 1.12x | 1.13x |
| branch_on_result | 2.73 | 2.73 | 2.38 [2.34-2.46] | 2.34 | -1.8% | yes | 1.15x | 1.17x |
| chain4_slow | 5.33 | 5.32 | 4.89 [4.00-6.07] | 4.22 | -13.6% | yes | 1.09x | 1.26x |
| crash_after_dispatch | 1.83 | 1.83 | 1.04 [1.03-1.05] | 1.03 | -0.6% | yes | 1.76x | 1.77x |
| early_break | 1.61 | 1.60 | 1.10 [1.10-1.10] | 1.10 | +0.0% | yes | 1.46x | 1.46x |
| identical10 | 1.55 | 1.55 | 1.00 [1.00-1.00] | 1.00 | +0.0% | yes | 1.55x | 1.55x |
| jail_break_mid | 10.33 | 10.32 | 6.80 [6.45-6.95] | 6.44 | -5.2% | yes | 1.52x | 1.60x |
| late_loop | 7.57 | 7.56 | 5.00 [5.00-5.01] | 5.00 | -0.0% | yes | 1.51x | 1.51x |
| map16 | 4.76 | 4.76 | 1.01 [1.01-1.19] | 1.05 | +3.7% | yes | 4.71x | 4.55x |
| map32 | 5.54 | 5.53 | 1.07 [1.04-1.09] | 1.07 | +0.4% | yes | 5.18x | 5.15x |
| map8_slow | 22.19 | 22.19 | 3.67 [3.28-3.90] | 3.93 | +7.2% | yes | 6.05x | 5.64x |
| map_reduce | 5.87 | 5.87 | 3.10 [3.10-3.11] | 3.10 | +0.0% | yes | 1.89x | 1.89x |
| multiblock | 5.57 | 5.56 | 2.68 [2.51-2.75] | 1.72 | -35.6% | no | 2.08x | 3.23x |
| mutating_loop | 7.05 | 7.05 | 2.51 [2.48-2.54] | 2.12 | -15.4% | no | 2.81x | 3.32x |
| no_peek_control | 2.16 | 2.16 | 1.12 [1.10-1.19] | 1.09 | -2.9% | no | 1.93x | 1.99x |
| prefill_heavy | 6.95 | 6.96 | 1.93 [1.90-1.95] | 2.03 | +5.0% | no | 3.60x | 3.43x |
| prose_sandwich | 8.80 | 8.79 | 6.31 [6.31-6.36] | 6.30 | -0.2% | yes | 1.39x | 1.40x |
| serial_chain6 | 3.53 | 3.53 | 2.33 [2.32-2.39] | 2.33 | +0.2% | yes | 1.52x | 1.51x |
| side_branch_chain | 7.50 | 7.50 | 4.37 [4.22-5.72] | 3.38 | -22.7% | no | 1.72x | 2.22x |
| syntax_gauntlet | 4.61 | 4.61 | 2.46 [2.43-2.64] | 1.94 | -21.2% | no | 1.87x | 2.38x |
| two_stage | 2.99 | 3.00 | 1.40 [1.40-1.40] | 1.40 | +0.0% | yes | 2.14x | 2.14x |
| while_computed | 2.55 | 2.56 | 1.33 [1.33-1.35] | 1.27 | -4.5% | no | 1.92x | 2.01x |

Speculative wall time, leave-one-pattern-out: median |error| 2.3%, mean 6.4%, max 35.6%; 16/22 within 5.5%; 15/22 inside the measured min-max of 5 reps (1% tolerance).
Server-sensitive subset (13 patterns whose speculative wall exceeds the stream by >10%): LOO median |error| 5.2%, mean 10.4%; 7/13 within 5.5%.
In-sample (one set of overheads for all 22): median |error| 0.8%, mean 5.8%; 17/22 within 5.5%.
Best global overheads: t_fixed=0.012, t_per_seq=0.0, t_admit=0.004, client_s=0.002; per-call output sigma=0.086 (from baseline spread).
