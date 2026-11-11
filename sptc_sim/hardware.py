"""Hardware and model specs, and the per-iteration cost model of the server.

One engine iteration (a "step") runs every scheduled sequence forward by its
scheduled tokens: 1 token for a decode, up to the chunk budget for a prefill.
Its time is a roofline over the bytes it must stream from memory and the
FLOPs it must do, plus measured-style framework overheads:

    t_step = max(t_mem, t_compute) + t_fixed + t_per_seq * n_seqs

    t_mem     = (weight bytes touched + KV bytes read) / (BW * bw_eff)
    t_compute = (2 * active_params * tokens + attention FLOPs) / (peak * mfu)

Weight bytes touched is constant for a dense model. For a mixture-of-experts
model it grows with the batch, because each extra token routes to k of E
experts and pulls in experts no one else in the batch needed:
E_touched = E * (1 - (1 - k/E) ** tokens) per layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

BF16 = 2


@dataclass(frozen=True)
class GPU:
    name: str
    mem_gb: float  # device (or unified) memory, GiB as marketed ("80 GB" = 80 GiB)
    bw_tbs: float  # memory bandwidth, TB/s
    bf16_tflops: float  # dense BF16 tensor peak (no sparsity)


# Datasheet numbers.
GPUS: dict[str, GPU] = {
    "H100-SXM": GPU("H100-SXM", 80, 3.35, 989.0),
    "A100-80G": GPU("A100-80G", 80, 2.039, 312.0),
    "L40S": GPU("L40S", 48, 0.864, 362.0),
    "L4": GPU("L4", 24, 0.300, 121.0),
    "RTX4090": GPU("RTX4090", 24, 1.008, 165.0),
    "H100-NVL": GPU("H100-NVL", 94, 3.9, 835.0),
    # Apple publishes no TFLOPS; ~17 is a rough estimate of the 40-core GPU's
    # FP16 matmul rate (unverified; treat M4 Max prefill numbers as order-of-magnitude)
    "M4-Max": GPU("M4-Max", 128, 0.546, 17.0),
}


@dataclass(frozen=True)
class Model:
    name: str
    layers: int
    hidden: int
    heads: int
    kv_heads: int
    head_dim: int
    vocab: int
    intermediate: int = 0  # dense MLP width (0 for pure MoE layers)
    experts: int = 0
    experts_per_tok: int = 0
    moe_intermediate: int = 0
    tied_embeddings: bool = False

    # -- parameter / byte accounting (bf16 weights) -----------------------------
    @property
    def attn_params_per_layer(self) -> int:
        q = self.hidden * self.heads * self.head_dim
        kv = 2 * self.hidden * self.kv_heads * self.head_dim
        o = self.heads * self.head_dim * self.hidden
        return q + kv + o

    @property
    def expert_params(self) -> int:
        return 3 * self.hidden * self.moe_intermediate

    @property
    def dense_mlp_params_per_layer(self) -> int:
        return 3 * self.hidden * self.intermediate

    @property
    def lm_head_params(self) -> int:
        return self.vocab * self.hidden

    @property
    def total_params(self) -> int:
        per_layer = self.attn_params_per_layer + self.dense_mlp_params_per_layer
        per_layer += self.experts * self.expert_params + self.hidden * self.experts
        emb = self.vocab * self.hidden * (1 if self.tied_embeddings else 2)
        return self.layers * per_layer + emb

    @property
    def active_params(self) -> int:
        """Params multiplied per token (embedding lookup excluded, lm_head included)."""
        per_layer = self.attn_params_per_layer + self.dense_mlp_params_per_layer
        per_layer += self.experts_per_tok * self.expert_params + self.hidden * self.experts
        return self.layers * per_layer + self.lm_head_params

    @property
    def kv_bytes_per_token(self) -> int:
        return 2 * self.layers * self.kv_heads * self.head_dim * BF16

    @property
    def is_moe(self) -> bool:
        return self.experts > 0

    def weight_bytes_touched(self, tokens: int) -> float:
        """Bytes of weights streamed in one step that processes `tokens` tokens."""
        per_layer = self.attn_params_per_layer + self.dense_mlp_params_per_layer
        if self.is_moe:
            e, k = self.experts, self.experts_per_tok
            touched = e * (1.0 - (1.0 - k / e) ** max(tokens, 1))
            per_layer += touched * self.expert_params + self.hidden * self.experts
        return (self.layers * per_layer + self.lm_head_params) * BF16

    @property
    def weight_bytes(self) -> float:
        return self.total_params * BF16


# Shapes from the Hugging Face config.json of each checkpoint.
MODELS: dict[str, Model] = {
    "Qwen3-4B": Model(
        "Qwen3-4B", layers=36, hidden=2560, heads=32, kv_heads=8, head_dim=128,
        vocab=151936, intermediate=9728, tied_embeddings=True,
    ),
    "Qwen3-8B": Model(
        "Qwen3-8B", layers=36, hidden=4096, heads=32, kv_heads=8, head_dim=128,
        vocab=151936, intermediate=12288,
    ),
    "Qwen3-1.7B": Model(
        "Qwen3-1.7B", layers=28, hidden=2048, heads=16, kv_heads=8, head_dim=128,
        vocab=151936, intermediate=6144, tied_embeddings=True,  # HF config: tied
    ),
    # Llama-3.1-8B shapes from Meta's published config (gated on HF; not re-fetched)
    "Llama-3.1-8B": Model(
        "Llama-3.1-8B", layers=32, hidden=4096, heads=32, kv_heads=8, head_dim=128,
        vocab=128256, intermediate=14336,
    ),
    "Qwen3-30B-A3B": Model(
        "Qwen3-30B-A3B", layers=48, hidden=2048, heads=32, kv_heads=4, head_dim=128,
        vocab=151936, experts=128, experts_per_tok=8, moe_intermediate=768,
    ),
}


@dataclass(frozen=True)
class Overheads:
    """Framework costs the roofline does not see (kernel launches, scheduler,
    sampling, detokenize, HTTP). Defaults are calibrated in experiments/calibrate.py."""

    t_fixed: float = 0.0035  # s per step (kernel launches, scheduler; large in eager mode)
    t_per_seq: float = 0.00004  # s per scheduled sequence per step
    bw_eff: float = 0.80  # achieved fraction of peak memory bandwidth
    mfu: float = 0.55  # achieved fraction of peak BF16 FLOPs (prefill GEMMs)
    client_s: float = 0.010  # per-request client + HTTP + tokenize, one way
    t_admit: float = 0.0  # engine-side CPU per newly admitted request (input prep)
    attn_mfu: float | None = None  # attention kernels' own efficiency (None: same as mfu)


@dataclass(frozen=True)
class HybridModel:
    """A model described by totals rather than shapes: quantized weights, KV only on
    its full-attention layers, and a fixed-size recurrent state per sequence that
    every decode step reads and writes (linear-attention / Gated DeltaNet layers)."""

    name: str
    total_params: int
    attn_layers: int  # layers with a KV cache
    heads: int
    kv_heads: int
    head_dim: int
    weight_bits: float = 16.0
    state_bytes_per_seq: float = 0.0  # read + written per decode step
    lm_head_params: int = 0
    is_moe: bool = False

    @property
    def layers(self) -> int:  # attention FLOPs only come from the attention layers
        return self.attn_layers

    @property
    def active_params(self) -> int:
        return self.total_params

    @property
    def weight_bytes(self) -> float:
        return self.total_params * self.weight_bits / 8

    def weight_bytes_touched(self, tokens: int) -> float:
        return self.weight_bytes

    @property
    def kv_bytes_per_token(self) -> int:
        return 2 * self.attn_layers * self.kv_heads * self.head_dim * BF16


# Qwen3.5-4B as served by Ollama 0.40 (GGUF metadata): 32 blocks, full attention every
# 4th (8 layers, 4 KV heads of dim 256); 24 Gated DeltaNet layers whose state is
# 32 value heads x 128 x 128 fp32 = 2 MiB per layer per sequence, read and written
# each step. Q4_K_M averages ~4.85 bits per weight.
QWEN35_4B_Q4 = HybridModel(
    "Qwen3.5-4B-Q4_K_M", total_params=4_205_751_296, attn_layers=8, heads=16, kv_heads=4,
    head_dim=256, weight_bits=4.85, state_bytes_per_seq=2 * 24 * 32 * 128 * 128 * 4,
)


# Qwen3-1.7B Q4_K_M (Ollama): plain attention, 28 layers, 8 KV heads of dim 128;
# 1.36 GB weight file for 2.03B params (5.35 bits per param incl. Q6 embeddings).
QWEN3_1P7B_Q4 = HybridModel(
    "Qwen3-1.7B-Q4_K_M", total_params=2_031_739_904, attn_layers=28, heads=16, kv_heads=8,
    head_dim=128, weight_bits=5.35,
)


# Two framework regimes. EAGER is fit to spec-ptc's runs.csv (vLLM
# --enforce-eager, Qwen3-4B); see experiments/calibrate.py. GRAPHS matches
# a CUDA-graph server: its two overheads are fit to NVIDIA's Llama-3.1-8B H100
# ITL-vs-concurrency table (5 points, 2 params; experiments/validate_cost.py).
GRAPHS = Overheads(t_fixed=0.0008, t_per_seq=0.00002, bw_eff=0.80, mfu=0.55, client_s=0.004)
# MoE kernels (routing, small grouped GEMMs) cost more per step: t_fixed fit to
# vLLM 0.16 Qwen3-30B-A3B batch-1 decode on H100 NVL (arXiv 2609.12923, 5.32 ms);
# the same paper's batch-32 point is then predicted within 7%.
GRAPHS_MOE = Overheads(t_fixed=0.0028, t_per_seq=0.00002, bw_eff=0.80, mfu=0.55,
                       client_s=0.004)


@dataclass
class StepCost:
    gpu: GPU
    model: Model
    tp: int = 1  # tensor parallel degree: splits bytes and FLOPs (no comm modeled)
    ov: Overheads = field(default_factory=Overheads)
    # measured decode step time by batch size (s), for engines whose kernels the
    # roofline does not describe (e.g. llama.cpp Metal at small batch); prefill
    # tokens in the same step add their compute time on top
    decode_table: dict | None = None

    def with_overheads(self, **kw) -> StepCost:
        return replace(self, ov=replace(self.ov, **kw))

    @property
    def bw(self) -> float:
        return self.gpu.bw_tbs * 1e12 * self.ov.bw_eff * self.tp

    @property
    def flops(self) -> float:
        return self.gpu.bf16_tflops * 1e12 * self.ov.mfu * self.tp

    def kv_capacity_tokens(self, gpu_mem_util: float = 0.92, reserve_gb: float = 3.0) -> int:
        """KV slots left after weights and an activation/CUDA-graph reserve."""
        gib = 2**30
        free = (self.gpu.mem_gb * gpu_mem_util - reserve_gb) * self.tp * gib
        free -= self.model.weight_bytes
        return max(0, int(free / self.model.kv_bytes_per_token))

    def step_time(self, items: list[tuple[int, int]], n_new: int = 0) -> float:
        """items: (new_tokens, context_before) per scheduled sequence;
        n_new: requests admitted for the first time in this step."""
        if not items:
            return 0.0
        if self.decode_table:
            return self._table_step(items, n_new)
        m = self.model
        tokens = 0
        kv_read = 0
        attn_flops = 0.0
        for n, ctx in items:
            tokens += n
            kv_read += ctx + n
            attn_flops += 4.0 * m.layers * m.heads * m.head_dim * n * (ctx + n / 2)
        state = getattr(m, "state_bytes_per_seq", 0.0) * len(items)  # recurrent layers
        t_mem = (m.weight_bytes_touched(tokens) + kv_read * m.kv_bytes_per_token + state) / self.bw
        # logits (lm_head) only for the last position of each sequence in the step
        body = m.active_params - m.lm_head_params
        gemm = 2.0 * (body * tokens + m.lm_head_params * len(items))
        attn_rate = self.flops if self.ov.attn_mfu is None else (
            self.gpu.bf16_tflops * 1e12 * self.ov.attn_mfu * self.tp)
        t_cmp = gemm / self.flops + attn_flops / attn_rate
        return (max(t_mem, t_cmp) + self.ov.t_fixed + self.ov.t_per_seq * len(items)
                + self.ov.t_admit * n_new)

    def _table_step(self, items: list[tuple[int, int]], n_new: int) -> float:
        tab = self.decode_table
        n_dec = sum(1 for n, _ in items if n == 1)
        pre = sum(n for n, _ in items if n > 1)
        t = 0.0
        if n_dec:
            ks = sorted(tab)
            if n_dec in tab:
                t = tab[n_dec]
            elif n_dec > ks[-1]:
                t = tab[ks[-1]] * n_dec / ks[-1]
            else:  # linear interpolation between the nearest measured batch sizes
                lo = max(k for k in ks if k < n_dec)
                hi = min(k for k in ks if k > n_dec)
                t = tab[lo] + (tab[hi] - tab[lo]) * (n_dec - lo) / (hi - lo)
        if pre:
            t += 2.0 * self.model.active_params * pre / self.flops
        return t + self.ov.t_admit * n_new

    # -- convenience for analysis ---------------------------------------------
    def decode_step(self, batch: int, ctx: int) -> float:
        return self.step_time([(1, ctx)] * batch)

    def ridge_tokens(self) -> float:
        """Tokens per step where a dense model's weight streaming equals its GEMM time."""
        return self.model.weight_bytes_touched(1) / self.bw * self.flops / (
            2.0 * self.model.active_params
        )
