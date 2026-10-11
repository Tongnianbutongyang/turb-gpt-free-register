# GPT Image 号池最小集

目标：只产 ChatGPT 网页 `accessToken`，不跑 Codex / 接码 / 提链。

仓库已克隆到本目录。`.env` 已改成 Image 最小集：

- `REGISTRATION_DRIVER=cloak`
- `ENABLE_CODEX_AUTO=False`
- `ENABLE_2FA=False`
- `ENABLE_FLOW_TRIGGER=False`
- `AUTO_PLAN_CHECK_AFTER_REGISTER=True`
- `CLOAK_USE_PROXY=True`
- `OTP_MAX_WAIT=180`

本机已经接上：

- 代理：当前 v2rayN `http://127.0.0.1:10808`（出口已验证）
- 邮箱：Docker `outlook-email-plus` 的 Outlook 组，已导出到 `用于注册的邮箱.txt`

## 1. 环境

PowerShell 7：

```powershell
cd E:\CTF\work\turb-gpt-free-register
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

没有本机 Roxy 就保持 `cloak`。有 Roxy 再把 `REGISTRATION_DRIVER` 改回 `roxy`。

## 2. 必填配置

编辑 `.env`：

1. `WEBUI_AUTH_CODE` 换成自己的码，不要留 `123456`。
2. 代理已写成当前 v2rayN：`PROXY_POOL=http://127.0.0.1:10808`。换节点后只要还是 10808 就不用改。
3. 邮箱已从 `outlook-email-plus` 的 Outlook 组导出，`EMAIL_SOURCE=outlook`，取件模式 `direct`（走 Graph，不走 mail.chatai.codes）。
4. 已注册分组（aisa / 7-7）没有导入。`USE_EMAIL_SERVICE=True` 保持开启。

不要开 Codex、接码、CPA、sub2api、提链。

## 3. 先跑通 1 个

```powershell
cd E:\CTF\work\turb-gpt-free-register
.\.venv\Scripts\python web.py --open-browser
```

打开 `http://127.0.0.1:5000`，用授权码登录。注册页只开 1 个、1 线程。成功标准：

- 任务成功
- 账号页能看到邮箱和 AT
- 套餐查询能回来（Free 也算成功）

这一步失败不要加并发。常见原因只有三个：代理出口、邮箱 OTP、Sentinel/页面改版。

## 4. 批量

1 个跑通后再加量。线程数不要超过可用代理数。建议先 `3` 线程、每次 `10` 个。

批量后在账号页抽查活。AT 会过期，号池必须带查活，不能当静态 Key。

## 5. 导出给 Image 调度

```powershell
.\.venv\Scripts\python tools\export_image_pool.py --live-only
```

产物在 `image_pool/`：

- `image-pool-*.jsonl`：完整字段
- `image-pool-*.txt`：`email----access_token`

下游按你现有 GPT Image 反代/调度格式再转一层。这里导出的是 ChatGPT 网页 AT，不是官方 `gpt-image-1` API Key。

## 6. 验收

注册成功数不是产能。按这个口径算：

`活号数 × 实际出图成功率`

每批抽 3～5 个 AT，打一次你真正用的出图接口。失败就标死，不要继续往池子里灌。

免费号没出图权时，这个项目也变不出官方 Images API。那时要另找网页 Image 接口或 Plus 资格，而不是继续加 Codex。
