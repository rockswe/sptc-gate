"""Validation layer 3: the step-cost model against a published ITL table.

NVIDIA NIM 1.8.0, Llama-3.1-8B-Instruct bf16, 1x H100-80GB, ISL/OSL 1000/1000:
inter-token latency by concurrency (docs.nvidia.com/nim/benchmarking/llm/
1.0.0/performance.html). NIM's backend is not named (often TensorRT-LLM), so
this checks the roofline + overhead SHAPE, not vLLM specifically. At steady
state each sequence is on average ~500 tokens into its output: ctx ~ 1500.

  .venv/bin/python experiments/validate_cost.py
"""

from pathlib import Path

from sptc_sim.hardware import GPUS, GRAPHS, GRAPHS_MOE, MODELS, StepCost

NIM = {1: 6.52, 25: 9.34, 50: 11.46, 100: 15.99, 200: 25.68}  # ms


def main() -> None:
    cost = StepCost(GPUS["H100-SXM"], MODELS["Llama-3.1-8B"], ov=GRAPHS)
    lines = ["| concurrency | NIM ITL (ms) | model (ms) | error |", "|---|---|---|---|"]
    for b, ms in NIM.items():
        sim = cost.decode_step(b, 1500) * 1000
        lines.append(f"| {b} | {ms:.2f} | {sim:.2f} | {100 * (sim - ms) / ms:+.1f}% |")
    moe = StepCost(GPUS["H100-NVL"], MODELS["Qwen3-30B-A3B"], ov=GRAPHS_MOE)
    lines += [
        "",
        "MoE anchor (arXiv 2609.12923, vLLM 0.16, H100 NVL, Qwen3-30B-A3B; t_fixed fit on the "
        "first row only; the paper's batch-32 figure is 'per-token time', read here as step/B):",
        "",
        "| point | measured (ms) | model (ms) | error |",
        "|---|---|---|---|",
    ]
    for label, b, ctx, ms in (("batch 1, 16k ctx (fit)", 1, 16000, 5.32),
                              ("batch 32, 8k ctx (check)", 32, 8192, 0.96 * 32)):
        sim = moe.decode_step(b, ctx) * 1000
        lines.append(f"| {label} | {ms:.2f} | {sim:.2f} | {100 * (sim - ms) / ms:+.1f}% |")
    out = "\n".join(lines)
    print(out)
    Path(__file__).resolve().parents[1].joinpath("results/validate_cost.md").write_text(out + "\n")


if __name__ == "__main__":
    main()
