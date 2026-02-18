# tests/test_compat_capability_bridge.py
from __future__ import annotations


def test_compat_exports_capability_flags_and_symbols() -> None:
    """
    Phase-1 guardrail:
    - compat must re-export capability flags from src.utils.compat.
    - Part 3 CPI flags must exist: HAS_SVL, HAS_RIPSER, HAS_TDA.
    - CAPABILITIES must contain the same flag values (stable introspection surface).
    """
    import compat  # type: ignore
    from src.utils import compat as cap  # type: ignore

    expected_flags = [
        # Base stack
        "HAS_NUMPY",
        "HAS_PANDAS",
        # SVL gating
        "HAS_SVL",
        "HAS_SVL_HURST",
        "HAS_YFINANCE",
        # TDA gating
        "HAS_RIPSER",
        "HAS_TDA",
        # Other optional dependencies used elsewhere
        "HAS_TORCH",
        "HAS_TENSORFLOW",
        "HAS_ARCH",
        "HAS_STATSMODELS",
        "HAS_RUPTURES",
    ]

    for name in expected_flags:
        assert hasattr(cap, name), f"src.utils.compat missing flag: {name}"
        assert hasattr(compat, name), f"compat missing flag: {name}"
        assert getattr(compat, name) == getattr(cap, name), f"Flag mismatch for {name}"

    # CAPABILITIES must exist and be a dict-like export
    assert hasattr(cap, "CAPABILITIES"), "src.utils.compat missing CAPABILITIES"
    assert hasattr(compat, "CAPABILITIES"), "compat missing CAPABILITIES"
    assert isinstance(getattr(cap, "CAPABILITIES"), dict), (
        "src.utils.compat CAPABILITIES must be a dict"
    )
    assert isinstance(getattr(compat, "CAPABILITIES"), dict), (
        "compat CAPABILITIES must be a dict"
    )

    cap_caps = getattr(cap, "CAPABILITIES")
    for name in expected_flags:
        assert name in cap_caps, f"CAPABILITIES missing key: {name}"
        assert cap_caps[name] == getattr(cap, name), (
            f"CAPABILITIES value mismatch for {name}"
        )

    # Safe symbol exports (None allowed when capability is False)
    if getattr(compat, "HAS_TENSORFLOW"):
        assert getattr(compat, "tf", None) is not None, (
            "compat.tf must be non-None when HAS_TENSORFLOW is True"
        )
    if getattr(compat, "HAS_TORCH"):
        assert getattr(compat, "torch", None) is not None, (
            "compat.torch must be non-None when HAS_TORCH is True"
        )
    if getattr(compat, "HAS_NUMPY"):
        assert getattr(compat, "np", None) is not None, (
            "compat.np must be non-None when HAS_NUMPY is True"
        )
    if getattr(compat, "HAS_PANDAS"):
        assert getattr(compat, "pd", None) is not None, (
            "compat.pd must be non-None when HAS_PANDAS is True"
        )
