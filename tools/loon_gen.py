#!/usr/bin/env python3
"""由家里的分流生成手机 Loon 配置（2026-11-11，「一份规则管两边」）。

来源（唯一真相）：
  - 规则顺序和规则集：本仓库 Mihomo.yaml
  - 策略组：VM101 /etc/mihomo/config.yaml 的 proxy-groups（经 ssh 读，或 --groups 指定导出的 yaml）
  - 私有部分（订阅链接、节点过滤、插件、MITM 证书、[General]）：--private 指定的 Loon 配置，**不进仓库**
脚本只重写 [Proxy Group] [Rule] [Remote Rule] 三段，其余段原样取自私有部分。

用法（在 .43）：
  python3 tools/loon_gen.py --private /opt/Workspace/Tools/LoonGen/private.conf --out /opt/Workspace/Tools/LoonGen/out/Loon.conf

翻译约定：
  - 组名去掉开头图标，「手动切换」写成「指定节点」（和面板一致）
  - smart / url-test 地区组 → Loon url-test + 对应节点过滤器；「只列某地区单个节点」的 select 组 → select + 过滤器
  - 家里的 RULE-SET → 同一来源的 Loon .list（blackmatrix 有 _Domain 的一并引用）
  - GEOSITE、非标端口、MATCH 在 Loon 没有对应，见 SKIP；手机兜底统一 FINAL,漏网之鱼
  - 手机专用的几条见 PHONE_EXTRA（微信 / 腾讯直连、TestFlight、Crypto）
"""
import argparse, re, subprocess, sys, urllib.request, os, datetime
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = 'https://raw.githubusercontent.com/'
BM = GH + 'blackmatrix7/ios_rule_script/master/rule/Loon/'
ME = GH + 'Invincible-Tyrannosaurus/clash-rule/main/'

# 家里规则集名 → Loon 名单（按顺序，可多个）
SPECIAL = {
    'ChinaMax': [BM + 'ChinaMax/ChinaMax_No_IPv6.list', BM + 'ChinaMax/ChinaMax_Domain.list'],   # 手机 ip-mode=v4-only
    'Apple': [BM + 'Apple/Apple.list', BM + 'Apple/Apple_Domain.list'],
    'GlobalMedia': [BM + 'GlobalMedia/GlobalMedia.list', BM + 'GlobalMedia/GlobalMedia_Domain.list'],
    'Proxy_Blackmatrix': [BM + 'Proxy/Proxy.list', BM + 'Proxy/Proxy_Domain.list'],
    'Direct_Blackmatrix': [BM + 'Direct/Direct.list'],
    'Custom_Proxy_Classical': [GH + 'Aethersailor/Custom_OpenClash_Rules/main/rule/Custom_Proxy.list'],
    'Steam_CDN_Classical': [GH + 'Aethersailor/Custom_OpenClash_Rules/main/rule/Steam_CDN.list'],
    'Encrypted_DNS_Classical': [GH + 'Aethersailor/Custom_OpenClash_Rules/main/rule/Encrypted_DNS.list'],
    'SpeedTest_LM': [GH + 'LM-Firefly/Rules/master/SpeedTest.list'],
    'PROXY_LM': [GH + 'LM-Firefly/Rules/master/PROXY.list'],
    'DMCA_Sensitive': [GH + 'LM-Firefly/Rules/master/Special/DMCA-Sensitive.list'],
    'ProxyGFWlist': [GH + 'ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list'],
}
SKIP = {   # 家里有、手机不引用的规则集，及原因
    'PT_IP': '只有纯 IP 段没有 Loon 格式；手机不跑 PT，PT 域名名单照样直连',
    'Custom_Port_Direct': '作者只出 Clash 格式；手机不做「非标端口直连」，兜底统一走漏网之鱼',
    'Encrypted_DNS_Classical': '会拦掉手机 Loon 自己用的 alidns.com / doh.pub / 223.5.5.5；手机 DNS 由 Loon 统一处理，App 自带 HTTPDNS 由插件屏蔽',
}
GEOSITE_NOTE = {   # 家里的 GEOSITE 规则在手机上由谁兜住
    'category-public-tracker': 'PT / PrivateTracker 名单', 'category-pt': 'PT / PrivateTracker 名单',
    'google-cn': 'ChinaMax', 'category-games@cn': 'ChinaMax', 'category-game-platforms-download': 'Steam_CDN / Download',
    'private': 'Lan 名单', 'category-ai-!cn': 'AI 各名单', 'cn': 'ChinaMax',
}
PHONE_EXTRA = {   # (插在家里哪个规则集后面 / 前面, Loon 名单, 策略, 标签)
    'top_local': [],   # 11-11 起本地规则都并进了仓库名单（linkcube 在 Direct 里）
    'after': {
        'Direct_Invincible': [(BM + 'WeChat/WeChat.list', '全球直连', '手机-微信'), (BM + 'Tencent/Tencent.list', '全球直连', '手机-腾讯'),
                              (BM + 'Tencent/Tencent_Domain.list', '全球直连', '手机-腾讯-域名')],
        'Proxy_Invincible': [(ME + 'Crypto.list', '节点选择', '手机-Crypto')],
    },
    'before': {'Apple': [(BM + 'TestFlight/TestFlight.list', '节点选择', '手机-TestFlight')]},
}
REGION_FILTER = {'hk': 'HK香港节点', 'tw': 'TW台湾节点', 'us': 'US美国节点', 'jp': 'JP日本节点', 'kr': 'KR韩国节点', 'sg': 'SG狮城节点'}
REGION_KEYS = {'hk': ['香港', 'HK', 'Hong'], 'tw': ['台湾', 'TW', 'Taiwan'], 'us': ['美国', 'USA', 'United States'],
               'jp': ['日本', 'JP', 'Japan'], 'kr': ['韩国', 'KR', 'Korea'], 'sg': ['狮城', '新加坡', 'SG', 'Singapore']}
ICON_FALLBACK = {   # 家里图标不在 Koolson/Qure 时用的公开图标
    'AI服务': GH + 'Koolson/Qure/master/IconSet/Color/Bot.png',
    'Talkatone': GH + 'luestr/IconResource/main/App_icon/120px/Talkatone.png',
    '甲骨文云': GH + 'Koolson/Qure/master/IconSet/Color/Server.png',
    '小米服务': GH + 'luestr/IconResource/main/App_icon/120px/MiHome.png',
    '亚马逊': GH + 'Koolson/Qure/master/IconSet/Color/Prime_Video.png',
}
ALIAS = {'手动切换': '指定节点'}
# 私有部分（旧手机配置）插件里的旧组名 → 新组名
OLDMAP = {'Bilibili': '哔哩哔哩', 'YouTube': '油管', 'Netflix': '奈飞', 'Tencent': '全球直连', 'ChatGPT': 'AI服务', 'PayPal': 'Paypal', 'Speed Test': 'Speedtest', '手动选择': '指定节点'}


def clean(name):
    """去掉组名开头的图标；手动切换 → 指定节点。"""
    if name in ('DIRECT', 'REJECT'):
        return name
    parts = name.split(' ', 1)
    s = parts[1] if len(parts) == 2 and not re.search(r'[A-Za-z0-9一-鿿]', parts[0]) else name
    return ALIAS.get(s, s)


def region_of(text):
    for code, keys in REGION_KEYS.items():
        if any(k in text for k in keys):
            return code
    return None


def http_ok(url, cache={}):
    if url not in cache:
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'curl/8'}), timeout=15)
            cache[url] = r.status == 200
        except Exception:
            cache[url] = False
    return cache[url]


def loon_lists(name, url):
    if name in SPECIAL:
        return SPECIAL[name]
    if 'Invincible-Tyrannosaurus/clash-rule' in url:
        return [ME + url.rsplit('/', 1)[1].replace('.yaml', '.list')]
    m = re.search(r'blackmatrix7/ios_rule_script/.*?/rule/Clash/([^/]+)/', url)
    if m:
        n = m.group(1); out = [BM + f'{n}/{n}.list']
        if http_ok(BM + f'{n}/{n}_Domain.list'):
            out.append(BM + f'{n}/{n}_Domain.list')
        return out
    raise SystemExit(f'规则集 {name} 不知道 Loon 版在哪：{url}（加进 SPECIAL 或 SKIP）')


def icon(g, name):
    u = str(g.get('icon') or '')
    m = re.search(r'/iconlib/qure/(?:[0-9a-f]{6}-)?(.+\.png)$', u)
    if m:
        c = GH + 'Koolson/Qure/master/IconSet/Color/' + m.group(1)
        if http_ok(c):
            return c
    if name in ICON_FALLBACK:
        return ICON_FALLBACK[name]
    code = region_of(g['name'])
    if g.get('type') in ('smart', 'url-test') and code:
        return GH + f'Orz-3/mini/master/Color/{code.upper()}.png'
    return ''


def groups_to_loon(groups, filters):
    out = []
    for g in groups:
        name = clean(g['name']); t = g['type']; ic = icon(g, name)
        tail = f',img-url = {ic}' if ic else ''
        if g.get('use'):
            code = region_of(g['name']) if t in ('smart', 'url-test', 'fallback', 'load-balance') else region_of(str(g.get('filter', '')))
            if name == '指定节点':
                f = '所有节点'
            elif name == '冷门地区':
                f = 'LM冷门地区'
            elif code:
                f = REGION_FILTER[code]
            else:
                raise SystemExit(f'组 {g["name"]} 认不出用哪个节点过滤器')
            if f not in filters:
                raise SystemExit(f'私有部分 [Remote Filter] 里没有 {f}')
            if t in ('smart', 'url-test', 'fallback', 'load-balance'):
                out.append(f'{name} = url-test,{f},url = http://www.gstatic.com/generate_204,interval = 600,tolerance = 50{tail}')
            else:
                out.append(f'{name} = select,{f}{tail}')
        else:
            out.append(f'{name} = select,' + ','.join(clean(x) for x in g.get('proxies') or []) + tail)
    return out


def rules_to_loon(rules, providers, home_groups):
    local, remote, notes = list(PHONE_EXTRA['top_local']), [], []
    for r in rules:
        p = [x.strip() for x in r.split(',')]; t = p[0]
        if t == 'RULE-SET':
            name, pol = p[1], clean(p[2])
            if name in SKIP:
                notes.append(f'跳过 {name}：{SKIP[name]}'); continue
            for u, ppol, tag in PHONE_EXTRA['before'].get(name, []):
                remote.append((u, ppol, tag))
            lists = loon_lists(name, providers[name]['url'])
            for i, u in enumerate(lists):
                remote.append((u, pol, name + ('' if i == 0 else '-域名')))
            for u, ppol, tag in PHONE_EXTRA['after'].get(name, []):
                remote.append((u, ppol, tag))
        elif t == 'GEOSITE':
            notes.append(f'GEOSITE,{p[1]} 手机上由 {GEOSITE_NOTE.get(p[1], "后面的名单")} 兜住')
        elif t == 'GEOIP' and p[1].lower() == 'private':
            notes.append('GEOIP,private 手机上由 Lan 名单和 skip-proxy 兜住（Loon 的 GeoIP 库没有 private）')
        elif t in ('IP-CIDR', 'IP-CIDR6', 'GEOIP', 'IP-ASN'):
            local.append(f'{t},{p[1]},{clean(p[2])},no-resolve')
        elif t in ('DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD'):
            local.append(f'{t},{p[1]},{clean(p[2])}')
        elif t in ('DST-PORT', 'MATCH'):
            notes.append(f'{r} → 手机统一 FINAL,漏网之鱼')
        else:
            raise SystemExit(f'不认识的规则：{r}')
    local.append('FINAL,漏网之鱼')
    return local, remote, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--private', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--groups', help='导出的 mihomo 配置（默认经 ssh 读 VM101）')
    a = ap.parse_args()
    home = yaml.safe_load(open(os.path.join(ROOT, 'Mihomo.yaml'), encoding='utf-8'))
    if a.groups:
        cfg = yaml.safe_load(open(a.groups, encoding='utf-8'))
    else:
        txt = subprocess.run(['ssh', '-i', '/root/.ssh/id_pve', '-o', 'BatchMode=yes', 'root@192.168.3.1',
                              "python3 -c \"import yaml,sys; y=yaml.safe_load(open('/etc/mihomo/config.yaml')); yaml.safe_dump({'proxy-groups': y['proxy-groups']}, sys.stdout, allow_unicode=True)\""],
                             capture_output=True, text=True, check=True).stdout
        cfg = yaml.safe_load(txt)
    groups = [g for g in cfg['proxy-groups'] if not g.get('hidden')]
    priv = open(a.private, encoding='utf-8').read().split('\n')
    sections, sec = {}, None; order = []
    for l in priv:
        if l.startswith('['):
            sec = l.strip(); sections[sec] = []; order.append(sec); continue
        if sec:
            sections[sec].append(l)
    filters = {l.split('=')[0].strip() for l in sections.get('[Remote Filter]', []) if '=' in l and not l.strip().startswith('#')}
    g_lines = groups_to_loon(groups, filters)
    local, remote, notes = rules_to_loon(home['rules'], home['rule-providers'], groups)
    # 手机上没有任何规则 / 组 / 插件用到的组不生成（如「非标端口」：手机不做端口分流）
    plug = '\n'.join(sections.get('[Plugin]', []))
    while True:
        refs = {pol for _, pol, _ in remote} | {l.rsplit(',', 2)[-2] if l.endswith('no-resolve') else l.rsplit(',', 1)[-1] for l in local}
        for gl in g_lines:
            refs |= set(gl.split('=', 1)[1].split(',img-url')[0].split(',')[1:])
        refs |= {'节点选择', '漏网之鱼'} | {OLDMAP.get(x.strip(), x.strip()) for x in re.findall(r'policy=([^,\n]+)', plug)}
        drop = [gl for gl in g_lines if gl.split(' = ')[0] not in refs]
        if not drop:
            break
        for gl in drop:
            notes.append(f'手机上没人用，不生成组：{gl.split(" = ")[0]}')
        g_lines = [gl for gl in g_lines if gl not in drop]
    names = {gl.split(' = ')[0] for gl in g_lines} | {'DIRECT', 'REJECT'}
    for _, pol, tag in remote:
        assert pol in names, f'{tag} 的策略 {pol} 不存在'
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    gen = {
        '[Proxy Group]': [f'# 由 clash-rule tools/loon_gen.py 按家里 VM101 策略组生成（{stamp}），不要在手机上改组结构，改家里再重新生成'] + g_lines + [''],
        '[Rule]': [f'# 由 loon_gen.py 生成（{stamp}）：家里 Mihomo.yaml 的行内规则 + 手机专用；IP 规则一律 no-resolve'] + local + [''],
        '[Remote Rule]': [f'# 由 loon_gen.py 生成（{stamp}）：顺序与家里 Mihomo.yaml 一致；「手机-」开头的是手机专用'] +
                         [f'{u}, policy={pol}, tag={tag}, enabled=true' for u, pol, tag in remote] + [''],
    }
    out = []
    for s in order:
        out.append(s)
        out += gen.get(s, sections[s])
    # 插件里指向旧组名的 policy 换成新组名
    txt = '\n'.join(out)
    txt = re.sub(r'policy=([^,\n]+)', lambda m: 'policy=' + OLDMAP.get(m.group(1).strip(), m.group(1).strip()), txt)
    for m in re.finditer(r'policy=([^,\n]+)', txt):
        assert m.group(1).strip() in names, f'插件 / 规则策略 {m.group(1)} 不存在'
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(txt)
    print(f'策略组 {len(g_lines)}，本地规则 {len(local)}，远程规则 {len(remote)} → {a.out}')
    for n in notes:
        print('  说明：' + n)


if __name__ == '__main__':
    main()
