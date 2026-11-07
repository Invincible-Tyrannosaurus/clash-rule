# clash-rule

家里网络的自维护分流规则。**改规则请改 `.yaml`，再把同一条加到对应的 `.list`**（推送时 GitHub 会自动检查两边是否一致）。

| 文件 | 谁在用 | 说明 |
|---|---|---|
| `Mihomo.yaml` | 家里代理机 VM101 的 mihomo | 全部规则顺序 + 51 个规则集；每天 04:30 由 `mihomo-rules-sync` 同步过去，校验不过（含 PT 保护）不应用 |
| `Direct / Proxy / AI / Reject / PT .yaml` | 家里 mihomo（经 Mihomo.yaml 引用） | 自己维护的直连 / 代理 / AI / 拦截 / PT 名单 |
| 同名 `.list` | 手机 Loon、订阅转换模板 | 和 `.yaml` 一致；可以多出"仅手机"的条目（家里已被其他规则集覆盖） |
| `clash-diy*.ini`、`surge-diy.conf` | 订阅转换（手机 / 电脑客户端） | 引用上面的 `.list` |
| `Crypto.list`、`NeteaseMusic.list`、`CF_Direct.yaml` | 仓库内没有引用 | 可能被手机或电脑的配置按链接直接使用，删除前先确认 |

**铁律**：PT 必须直连（`PT.yaml` 在 Mihomo.yaml 里排在最前）。

自检：`python3 tools/check.py`
