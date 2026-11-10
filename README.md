# clash-rule

家里网络的自维护分流规则。**改规则请改 `.yaml`，再把同一条加到对应的 `.list`**（推送时 GitHub 会自动检查两边是否一致）。

| 文件 | 谁在用 | 说明 |
|---|---|---|
| `Mihomo.yaml` | 家里代理机 VM101 的 mihomo | 全部规则顺序 + 53 个规则集；每天 04:30 由 `mihomo-rules-sync` 同步过去，校验不过（含 PT 保护）不应用 |
| `Direct / Proxy / AI / Reject / PT / Oracle / Talkatone .yaml` | 家里 mihomo（经 Mihomo.yaml 引用） | 自己维护的直连 / 代理 / AI / 拦截 / PT / 甲骨文云名单（家里走可切换的「☁️ 甲骨文云」组，默认直连）/ Talkatone |
| 同名 `.list` | 手机 Loon、订阅转换模板 | 和 `.yaml` 一致；可以多出"仅手机"的条目（家里已被其他规则集覆盖） |
| `clash-diy*.ini`、`surge-diy.conf` | 订阅转换（手机 / 电脑客户端） | 引用上面的 `.list` |
| `Crypto.list`、`NeteaseMusic.list`、`CF_Direct.yaml` | 仓库内没有引用 | 可能被手机或电脑的配置按链接直接使用，删除前先确认 |

**铁律**：PT 必须直连（`PT.yaml` 在 Mihomo.yaml 里排在最前）。

自检：`python3 tools/check.py`

## 手机 Loon 配置（一份规则管两边）

手机 Loon 的策略组和分流由 `tools/loon_gen.py` 按家里生成，**改分流只改家里**（本仓库 `Mihomo.yaml` + VM101 的策略组），再重新生成一次：

```
python3 tools/loon_gen.py --private /opt/Workspace/Tools/LoonGen/private.conf --out /opt/Workspace/Tools/LoonGen/out/Loon-$(date +%Y%m%d).conf
```

- 规则顺序、规则集、策略组都和家里一致；组名去掉图标，「手动切换」写成「指定节点」（和面板一致）。
- 订阅链接、节点过滤、插件、MITM 证书、[General] 来自 `--private`（只在 .43，权限 600，**不进本仓库**）。
- 家里有、手机不引用的（PT 纯 IP 段、非标端口、拦截加密 DNS）和手机专用的（微信 / 腾讯直连、TestFlight、Crypto）写在脚本开头 `SKIP` / `PHONE_EXTRA`，各带原因。

