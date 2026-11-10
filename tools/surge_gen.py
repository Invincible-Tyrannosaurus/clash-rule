#!/usr/bin/env python3
"""由家里的分流生成 Mac 上 Surge 的配置（2026-11-11，和 loon_gen.py 同一份规则）。

来源：本仓库 Mihomo.yaml（规则顺序）+ VM101 策略组（经 ssh）+ 两个私有文件（都不进仓库）：
  --private      Surge 私有部分：[General] [Host] [SSID Setting] 和要排在最前面的 [Rule]（工作网络等）
  --loon-private 手机 Loon 的私有配置；--private 里没有 [机场订阅] 段时，才从这里取订阅链接
脚本生成 [Proxy Group] 和 [Rule]，其余段原样取自 --private。

用法（在 .43）：
  python3 tools/surge_gen.py --private /opt/Workspace/Tools/LoonGen/surge-private.conf \
      --loon-private /opt/Workspace/Tools/LoonGen/private.conf --out /opt/Workspace/Tools/LoonGen/out/Surge.conf

和 Loon 的区别：Surge 严格从上往下匹配，所以每条 RULE-SET 都加 no-resolve；blackmatrix 的 _Domain 名单用 DOMAIN-SET；
节点来自一个隐藏的订阅组，地区组用 Surge 的 smart 组 + 家里同样的筛选正则。
"""
import argparse, datetime, os, re, subprocess, sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loon_gen as L

SUB = '机场订阅'          # 隐藏的订阅组名
SURGE_SKIP = {             # 手机不用、Mac 也不用的保持一致；Mac 额外用「拦截加密 DNS」也会拦掉系统 DNS 设置里的 DoH，同样不用
    **L.SKIP,
}


def to_surge(url):
    """Loon 版名单地址 → Surge 版（blackmatrix 换目录；Mac 不限 IPv4，ChinaMax 用完整版）。返回 (类型, 地址)。"""
    if '/rule/Loon/' in url:
        url = url.replace('/rule/Loon/', '/rule/Surge/').replace('ChinaMax_No_IPv6.list', 'ChinaMax.list')
        if url.endswith('_Domain.list'):
            return 'DOMAIN-SET', url
    return 'RULE-SET', url


def groups_to_surge(groups):
    out = [f'{SUB} = select, policy-path={{SUB_URL}}, update-interval=86400, hidden=true']
    for g in groups:
        name = L.clean(g['name']); t = g['type']
        ic = L.icon(g, name); tail = f', icon-url={ic}' if ic else ''
        if g.get('use'):
            flt = str(g.get('filter') or '.*')
            assert ',' not in flt, f'{name} 的筛选正则里有逗号，Surge 这一行会被拆错'
            if t in ('smart', 'url-test', 'fallback', 'load-balance'):
                out.append(f'{name} = smart, include-other-group={SUB}, policy-regex-filter={flt}{tail}')
            else:
                out.append(f'{name} = select, include-other-group={SUB}, policy-regex-filter={flt}{tail}')
        else:
            out.append(f'{name} = select, ' + ', '.join(L.clean(x) for x in g.get('proxies') or []) + tail)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--private', required=True); ap.add_argument('--loon-private', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--groups')
    a = ap.parse_args()
    home = yaml.safe_load(open(os.path.join(L.ROOT, 'Mihomo.yaml'), encoding='utf-8'))
    if a.groups:
        cfg = yaml.safe_load(open(a.groups, encoding='utf-8'))
    else:
        txt = subprocess.run(['ssh', '-i', '/root/.ssh/id_pve', '-o', 'BatchMode=yes', 'root@192.168.3.1',
                              "python3 -c \"import yaml,sys; y=yaml.safe_load(open('/etc/mihomo/config.yaml')); yaml.safe_dump({'proxy-groups': y['proxy-groups']}, sys.stdout, allow_unicode=True)\""],
                             capture_output=True, text=True, check=True).stdout
        cfg = yaml.safe_load(txt)
    groups = [g for g in cfg['proxy-groups'] if not g.get('hidden')]
    # 机场订阅：优先用 --private 里 [机场订阅] 段的 Surge 专用链接（这一段只给脚本看，不写进生成的配置），没有才用 Loon 的
    priv_txt = open(a.private, encoding='utf-8').read()
    m = re.search(r'^\[机场订阅\]\s*\n(?:#.*\n|\s*\n)*\s*(https?://\S+)', priv_txt, re.M)
    if m:
        sub_url = m.group(1); sub_from = 'Surge 私有部分里的 Surge 专用订阅'
    else:
        loon = open(a.loon_private, encoding='utf-8').read()
        m = re.search(r'^\[Remote Proxy\]\s*\n(?:#.*\n|\s*\n)*[^=\n]+=\s*(https?://[^,\s]+)', loon, re.M)
        if not m:
            raise SystemExit('私有部分和 Loon 私有配置里都找不到机场订阅链接')
        sub_url = m.group(1); sub_from = 'Loon 私有配置里的订阅（Surge 不一定认这个格式）'
    if ',' in sub_url:
        raise SystemExit('订阅链接里有逗号，policy-path 会被拆错')

    # 规则：沿用 loon_gen 的翻译（同一张对照表、同样的跳过和手机专用项）
    local, remote, notes = L.rules_to_loon(home['rules'], home['rule-providers'], groups)
    rules = []
    for u, pol, tag in remote:
        kind, su = to_surge(u)
        rules.append(f'# {tag}')
        rules.append(f'{kind},{su},{pol}' + (',no-resolve' if kind == 'RULE-SET' else ''))
    for l in local:
        if l.startswith('FINAL'):
            continue
        rules.append(l)
    rules.append('FINAL,漏网之鱼,dns-failed')

    priv = open(a.private, encoding='utf-8').read().split('\n')
    sections, order, sec = {}, [], None
    for l in priv:
        if l.startswith('['):
            sec = l.strip(); sections[sec] = []
            if sec != '[机场订阅]':
                order.append(sec)
            continue
        if sec:
            sections[sec].append(l)
    top = [l for l in sections.get('[Rule]', []) if l.strip()]
    g_lines = groups_to_surge(groups)
    names = {L.clean(g['name']) for g in groups} | {'DIRECT', 'REJECT', SUB}
    for r in top + rules:
        s = r.strip()
        if s.startswith('#') or not s:
            continue
        p = [x.strip() for x in s.split(',')]
        pol = p[1] if p[0] == 'FINAL' else (p[2] if p[0] not in ('AND', 'OR', 'NOT') else p[-1])
        assert pol in names, f'规则策略不存在：{r}'
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    gen = {
        '[Proxy Group]': [f'# 由 clash-rule tools/surge_gen.py 按家里策略组生成（{stamp}）；改分流改家里再重新生成'] + g_lines + [''],
        '[Rule]': [f'# 前面是私有部分（工作网络等），后面由 surge_gen.py 生成（{stamp}），顺序与家里 Mihomo.yaml 一致'] + top +
                  [''] + rules + [''],
    }
    out = ['# 由 clash-rule tools/surge_gen.py 生成：不要在 Surge 界面里改策略组和规则（下次生成会被覆盖），改家里再重新生成', '']
    if '[Proxy Group]' not in order:                     # 策略组排在规则前面
        order.insert(order.index('[Rule]') if '[Rule]' in order else len(order), '[Proxy Group]')
    if '[Rule]' not in order:
        order.append('[Rule]')
    for s in order:
        out.append(s); out += gen.get(s, sections.get(s, []))
    txt = '\n'.join(out).replace('{SUB_URL}', sub_url)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(txt + '\n')
    print(f'策略组 {len(g_lines)}（含隐藏订阅组），私有规则 {len(top)}，生成规则 {len(rules)} → {a.out}')
    print(f'  机场订阅来自：{sub_from}')
    for n in notes:
        print('  说明：' + n)


if __name__ == '__main__':
    main()
