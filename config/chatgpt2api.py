# -*- coding: utf-8 -*-
"""chatgpt2api 号池对接配置。"""
from config.env_loader import apply_env_overrides

# 注册成功后是否把网页 accessToken 自动注入 chatgpt2api。
CHATGPT2API_AUTO_EXPORT: bool = True

# chatgpt2api 服务地址，例如 http://127.0.0.1:3030
CHATGPT2API_API_BASE: str = "http://127.0.0.1:3030"

# chatgpt2api 管理密钥；请求头使用 Authorization: Bearer <key>
CHATGPT2API_AUTH_KEY: str = ""

# 导入超时秒数。chatgpt2api 导入后会立刻刷新账号，建议给足时间。
CHATGPT2API_API_TIMEOUT: int = 180

# 导入账号的 source_type。网页 AT 固定用 web。
CHATGPT2API_SOURCE_TYPE: str = "web"

# 把 127.0.0.1 / localhost 代理改写成 host.docker.internal，
# 让 Docker 里的 chatgpt2api 能走到宿主机 v2rayN。
CHATGPT2API_REWRITE_LOOPBACK_PROXY: bool = True

# 覆盖导入时写入 chatgpt2api 的代理。留空则用注册时实际使用的代理。
CHATGPT2API_ACCOUNT_PROXY: str = ""

apply_env_overrides(globals(), {
    "CHATGPT2API_AUTO_EXPORT": "bool",
    "CHATGPT2API_API_BASE": "str",
    "CHATGPT2API_AUTH_KEY": "str",
    "CHATGPT2API_API_TIMEOUT": "int",
    "CHATGPT2API_SOURCE_TYPE": "str",
    "CHATGPT2API_REWRITE_LOOPBACK_PROXY": "bool",
    "CHATGPT2API_ACCOUNT_PROXY": "str",
})
