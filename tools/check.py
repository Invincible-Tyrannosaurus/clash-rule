#!/usr/bin/env python3
"""规则自检（2026-11-07）：本机和 GitHub Actions 都跑。
- X.yaml 里的每条规则都必须出现在 X.list（家里 mihomo 用 .yaml，手机 Loon 用 .list；.list 可以多出"仅手机"的条目）
- 同一文件里不许重复；同一条规则不许同时出现在 Direct / Proxy / AI / Reject / PT 的两个列表里
- 不许有只差大小写的文件名（Mac / Windows 上会互相覆盖）
- 规则类型必须是认识的
失败时退出码 1。"""
import collections, os, re, sys

PAIRS = ["AI", "PT", "Proxy", "Reject", "Direct", "Oracle", "Talkatone"]
TYPES = re.compile(r"^(DOMAIN|DOMAIN-SUFFIX|DOMAIN-KEYWORD|DOMAIN-REGEX|DOMAIN-WILDCARD|IP-CIDR6?|IP-ASN|IP-SUFFIX|GEOIP|GEOSITE|PROCESS-NAME|DST-PORT|SRC-IP-CIDR|USER-AGENT|URL-REGEX|AND|OR|NOT),")
bad = []


def rules(path, yaml):
    out = []
    for n, l in enumerate(open(path, encoding="utf-8"), 1):
        s = l.strip()
        if not s or s.startswith("#") or s.startswith("//") or s == "payload:":
            continue
        if yaml:
            m = re.match(r"^-\s*['\"]?(.+?)['\"]?\s*$", s)
            if not m:
                continue
            s = m.group(1)
        out.append((n, s))
    return out


def key(r):
    return ",".join(x.strip() for x in r.split(",")[:2]).lower()


names = collections.defaultdict(list)
for f in os.listdir("."):
    names[f.lower()].append(f)
bad += [f"文件名只差大小写：{v}" for v in names.values() if len(v) > 1]

sets = {}
for p in PAIRS:
    if not (os.path.exists(f"{p}.yaml") and os.path.exists(f"{p}.list")):
        continue
    Y, L = rules(f"{p}.yaml", True), rules(f"{p}.list", False)
    for name, rs in ((f"{p}.yaml", Y), (f"{p}.list", L)):
        c = collections.Counter(key(r) for _, r in rs)
        bad += [f"{name} 重复：{k}" for k, v in c.items() if v > 1]
        bad += [f"{name}:{n} 规则类型不认识：{r}" for n, r in rs if not TYPES.match(r)]
    ly, yy = {key(r) for _, r in L}, {key(r) for _, r in Y}
    bad += [f"{p}.list 缺少 {p}.yaml 里的：{r}" for _, r in Y if key(r) not in ly]
    extra = [r for _, r in L if key(r) not in yy]
    if extra:
        print(f"提示：{p}.list 比 .yaml 多 {len(extra)} 条（仅手机）")
    sets[p] = yy
for a in sets:
    for b in sets:
        if a < b and sets[a] & sets[b]:
            bad.append(f"{a} 和 {b} 有相同规则：{sorted(sets[a] & sets[b])[:5]}")
if bad:
    print("\n".join("✗ " + x for x in bad))
    sys.exit(1)
print("✓ 规则自检通过")
