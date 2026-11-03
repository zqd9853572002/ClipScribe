# -*- coding: utf-8 -*-
"""denoise 模块：降噪滤镜链构造（RNNoise / afftdn 降级 / arnndn mix）。"""

from mp3tom4.denoise import build_denoise_chain


def test_fallback_chain_uses_highpass_and_afftdn():
    """模型缺失时必须降级为频谱降噪，而不是只剩高通滤波。"""
    chain = build_denoise_chain("", 16000)
    assert chain.startswith("highpass=f=80")
    assert "afftdn=nf=-25:tn=1" in chain
    assert "arnndn" not in chain
    assert chain.endswith(",aresample=16000")


def test_model_chain_uses_arnndn_without_afftdn():
    chain = build_denoise_chain(r"C:\models\bd.rnnn", 48000)
    assert "arnndn=m='C\\:/models/bd.rnnn'" in chain
    assert "afftdn" not in chain
    assert chain.endswith(",aresample=48000")


def test_arnndn_mix_default_and_custom():
    """默认 0.8；mix=1.0 是 ffmpeg 默认值，省略以保持旧滤镜串。"""
    assert ":mix=0.8" in build_denoise_chain("/m/bd.rnnn", 48000)
    assert ":mix=0.55" in build_denoise_chain("/m/bd.rnnn", 48000, mix=0.55)
    assert ":mix=" not in build_denoise_chain("/m/bd.rnnn", 48000, mix=1.0)


def test_arnndn_mix_is_clamped():
    assert ":mix=1" not in build_denoise_chain("/m/bd.rnnn", 48000, mix=5.0)
    assert ":mix=0" in build_denoise_chain("/m/bd.rnnn", 48000, mix=-3.0)
    # 无法解析的配置值回退默认 0.8
    assert ":mix=0.8" in build_denoise_chain("/m/bd.rnnn", 48000, mix="abc")


def test_configured_arnndn_mix_is_used():
    """config.json 里的 arnndn_mix 生效（无需 UI 暴露）。"""
    from mp3tom4 import config

    config.save_config({"arnndn_mix": 0.6})
    assert ":mix=0.6" in build_denoise_chain("/m/bd.rnnn", 48000)

    # 越界配置同样被夹紧
    config.save_config({"arnndn_mix": 3})
    assert ":mix=" not in build_denoise_chain("/m/bd.rnnn", 48000)
