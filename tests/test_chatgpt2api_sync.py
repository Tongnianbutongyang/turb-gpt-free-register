from core.chatgpt2api_sync import rewrite_loopback_proxy


def test_rewrite_loopback_socks_proxy():
    assert (
        rewrite_loopback_proxy("socks5h://127.0.0.1:10808")
        == "socks5h://host.docker.internal:10808"
    )


def test_rewrite_keeps_non_loopback():
    assert rewrite_loopback_proxy("socks5h://10.0.0.8:1080") == "socks5h://10.0.0.8:1080"
