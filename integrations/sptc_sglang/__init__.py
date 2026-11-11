"""sptc_sglang: the sptc speculation-aware scheduling policy as an SGLang v0.5.22 plugin.

Loaded through SGLang's general plugin entry point ("sglang.srt.plugins": sptc), active
only when SPTC_SGLANG_CONFIG is set. See README.md ("SGLang").
"""

__all__ = ["register"]


def register() -> None:
    from .plugin import register as _register

    _register()
