# Weibo -> Bilibili 自动转发任务

这个小工具会：

1. 拉取指定微博用户最新一条动态
2. 拼接成如下格式

```text
转自XXX微博：

正文
```

3. 自动发布到你的 B 站动态
4. 记录每个 UID 的 `mid`，避免重复转发

> 你刚指定的用户已内置默认 UID：`5657426591`（来自 `https://m.weibo.cn/u/5657426591`）。

## 1) 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 可选：当前版本无第三方依赖
```

## 2) 配置环境变量

```bash
# 可选：单个 UID（不填时默认 5657426591）
export WEIBO_UID='5657426591'

# 可选：可直接粘贴 m.weibo.cn 用户链接（例如你给的链接）
export WEIBO_USER_INPUT='https://m.weibo.cn/u/5657426591?t=0'

# 可选：多个 UID（英文逗号分隔）；会和 WEIBO_UID 合并去重
export WEIBO_UIDS='5657426591,1234567890'

export BILI_COOKIE='SESSDATA=...; bili_jct=...; DedeUserID=...'
# 可选：自定义文案前缀，默认是“转自{name}微博：\n\n”
export FORWARD_PREFIX='转自{name}微博：\n\n'
# 可选：状态文件
export STATE_FILE='.forward_state.json'
# 可选：仅打印不发布
export DRY_RUN='false'
```

> `BILI_COOKIE` 必须包含 `bili_jct`，用于 CSRF 校验。
>
> 当前脚本只使用 Python 标准库网络模块（`urllib`），不再强依赖 `requests`。


## Windows 快速运行

你在 Windows CMD 里可以这样设置（当前窗口有效）：

```bat
set WEIBO_USER_INPUT=https://m.weibo.cn/u/5657426591?t=0
set DRY_RUN=true
python forward_weibo_to_bili.py
```

如果要正式发布到 B 站，再补上 Cookie：

```bat
set BILI_COOKIE=SESSDATA=...; bili_jct=...; DedeUserID=...
set DRY_RUN=false
python forward_weibo_to_bili.py
```

> 新版本在未提供 `BILI_COOKIE` 时会自动退化为 dry-run 预览模式，不会直接报错退出。

## 3) 先试跑（不发动态）

```bash
DRY_RUN=true python forward_weibo_to_bili.py
```

## 4) 正式运行

```bash
python forward_weibo_to_bili.py
```

## 5) 定时任务（cron，每 10 分钟）

```cron
*/10 * * * * cd /workspace/Forwarding-tool && /usr/bin/env bash -lc 'source .venv/bin/activate && python forward_weibo_to_bili.py >> forward.log 2>&1'
```

## 说明

- 脚本拉取端固定使用 `m.weibo.cn` 的公开接口（免登录场景）。
- 不使用 `weibo.cn` 抓取链路，避免登录门槛。

## 常见问题

- **提示“未获取到微博内容”**：通常是 UID 错误，或该账号不可见。
- **提示“BILI_COOKIE 中未找到 bili_jct”**：Cookie 不完整。
- **提示 B 站 code 非 0**：Cookie 失效或风控限制，重新登录获取 Cookie。

## 安全建议

- 不要把 `BILI_COOKIE` 写进代码仓库。
- 建议将脚本部署在你自己的服务器并限制访问。
