from pathlib import Path

from agent.config import load_config


def test_load_config_example():
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config.example.yaml")
    assert "base" in cfg.chains
    assert cfg.chains["base"].chain_id == 8453
    assert cfg.cost_floor.threshold_pct == 6.5
