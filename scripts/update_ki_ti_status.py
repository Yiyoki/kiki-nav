#!/usr/bin/env python3
from pathlib import Path
from subprocess import run, PIPE
import json
import time

SUB_PATH = Path('/opt/clash/subscription.txt')
PROXY = 'http://127.0.0.1:7892'
TESTS = [
    ('google', 'Google', 'https://www.google.com/generate_204', [204], 1000),
    ('github', 'GitHub', 'https://www.github.com/', [200, 301, 302], 1200),
    ('cloudflare', 'Cloudflare', 'https://www.cloudflare.com/', [200], 1500),
    ('wikipedia', 'Wikipedia', 'https://www.wikipedia.org/', [200], 1000),
    ('ipify', 'IP回显', 'https://api.ipify.org/?format=json', [200], 1000),
]


def read_subscription_url():
    text = SUB_PATH.read_text(encoding='utf-8', errors='ignore')
    for line in text.splitlines():
        if line.startswith('kycloud:'):
            return line.split(':', 1)[1]
    raise SystemExit('kycloud not found')


def probe(url):
    best = None
    for attempt in range(2):
        cmd = [
            'curl', '-sS', '--max-time', '15',
            '-x', PROXY,
            '-A', 'Mozilla/5.0',
            '-o', '/tmp/ki-ti-gua-le-ma.out',
            '-w', '%{http_code} %{time_total}',
            url,
        ]
        start = time.time()
        proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        elapsed = round((time.time() - start) * 1000)
        raw = proc.stdout.strip()
        code, seconds = ('000', '0')
        if raw:
            parts = raw.split()
            if len(parts) >= 2:
                code, seconds = parts[0], parts[1]
        result = {
            'ok': proc.returncode == 0 and code not in {'000', 'ERR'},
            'code': code,
            'ms': elapsed,
            'seconds': seconds,
            'stderr': proc.stderr.strip(),
        }
        if result['ok']:
            return result
        best = result
        time.sleep(1)
    return best or {'ok': False, 'code': 'ERR', 'ms': 0, 'seconds': '0', 'stderr': 'probe failed'}


def level(code, ms, ok_codes, warn_ms):
    if code in {'000', 'ERR'}:
        return 'red'
    try:
        if int(code) not in ok_codes:
            return 'red'
    except Exception:
        return 'red'
    if ms >= warn_ms:
        return 'yellow'
    return 'green'


def main():
    sub_url = read_subscription_url()
    report = {
        'name': 'kycloud',
        'subscription_label': 'kycloud',
        'proxy': PROXY,
        'tests': [],
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S 北京时间', time.localtime(time.time() + 8 * 3600)),
    }
    for key, name, url, ok_codes, warn_ms in TESTS:
        result = probe(url)
        result.update({'key': key, 'name': name, 'url': url, 'level': level(result['code'], result['ms'], ok_codes, warn_ms)})
        report['tests'].append(result)
    success = sum(1 for x in report['tests'] if x['level'] != 'red')
    report['overall'] = 'green' if success == len(report['tests']) and all(x['level'] == 'green' for x in report['tests']) else ('yellow' if success >= 3 else 'red')
    report['summary'] = {
        'success_count': success,
        'total_count': len(report['tests']),
        'avg_ms': round(sum(x['ms'] for x in report['tests']) / len(report['tests'])),
    }
    out = Path('/home/admin/.hermes/artifacts/kiki-nav/data/ki-ti-gua-le-ma-status.json')
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out)
    print(report['overall'])


if __name__ == '__main__':
    main()
