"""Lecture seule : API Loki ou export Grafana, extraction des accès WAF en CSV."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

# Format observé dans l'export WAF fourni ; pas de reconnaissance de motif SQL.
ACCESS = re.compile(r'^(?P<peer>\S+) - - \[(?P<time>[^]]+)\] "(?P<method>\S+) (?P<target>\S+) (?P<protocol>[^" ]+)" (?P<status>\d{3}) (?P<size>\d+|-) "(?P<referer>(?:\\.|[^"\\])*)" "(?P<agent>(?:\\.|[^"\\])*)" "(?P<client>[^" ]+)"$')
MONTHS = {m: i for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), 1)}
FIELDS = ['observed_at', 'loki_timestamp_ns', 'peer_ip', 'client_ip', 'method',
          'request_target', 'path', 'query', 'status', 'response_bytes', 'user_agent',
          'container', 'service', 'service_name']


def parse_access(line, labels=None, loki_ns=None):
    # L'export TXT préfixe la ligne par l'heure locale de Grafana. Ne pas l'utiliser comme UTC.
    if '\t' in line:
        prefix, tail = line.split('\t', 1)
        if re.match(r'^\d{4}-\d\d-\d\d ', prefix):
            line = tail
    match = ACCESS.fullmatch(line.strip())
    if not match:
        raise ValueError('Format différent du journal d’accès WAF attendu')
    d = match.groupdict()
    # Le dernier champ est extrait mais sa fiabilité dépend de la configuration des proxies.
    peer = str(ipaddress.ip_address(d['peer']))

    # Un appel interne au WAF peut ne pas transmettre d'IP client ("-").
    # Conserver alors le pair réseau ; le moteur protège déjà cette adresse
    # lorsque client_ip == peer_ip pour éviter de bloquer le proxy.
    client = (
        peer
        if d['client'] == '-'
        else str(ipaddress.ip_address(d['client']))
    )
    
    stamp = re.fullmatch(r'(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})', d['time'])
    if not stamp or stamp[2] not in MONTHS:
        raise ValueError('Horodatage WAF invalide')
    day, month, year, hour, minute, second, offset = stamp.groups()
    sign = 1 if offset[0] == '+' else -1
    tz = timezone(sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:])))
    timestamp = datetime(int(year), MONTHS[month], int(day), int(hour), int(minute), int(second), tzinfo=tz)
    # HTTP origin-form : séparation sans décoder ni normaliser la charge utile.
    target = d['target']
    path, sep, query = target.partition('?')
    labels = labels or {}
    return dict(zip(FIELDS, [timestamp.astimezone(timezone.utc).isoformat(), loki_ns or '',
        peer, client, d['method'], target, path, query if sep else '', int(d['status']),
        int(d['size']) if d['size'] != '-' else '', d['agent'],
        labels.get('container', ''), labels.get('service', ''), labels.get('service_name', '')]))


def time_ns(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Indiquer le fuseau : Z ou +02:00, par exemple')
    delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000


def request_page(base, query, start, end, limit, timeout):
    params = urlencode({'query': query, 'start': str(start), 'end': str(end),
                        'limit': limit, 'direction': 'forward'})
    headers = {}
    if os.environ.get('LOKI_BEARER_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['LOKI_BEARER_TOKEN']
    if os.environ.get('LOKI_TENANT_ID'):
        headers['X-Scope-OrgID'] = os.environ['LOKI_TENANT_ID']
    req = Request(base.rstrip('/') + '/loki/api/v1/query_range?' + params, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get('status') != 'success' or payload.get('data', {}).get('resultType') != 'streams':
        raise ValueError('Loki doit renvoyer des logs, resultType=streams')
    rows = []
    for stream in payload['data']['result']:
        for value in stream['values']:
            ns, line = value[:2]
            ns = int(ns)
            if start <= ns < end:
                rows.append((ns, line, stream['stream']))
    return rows


def fetch_range(base, query, start, end, limit=1000, timeout=5, page=None):
    """Découpe les intervalles saturés, sans avancer d'une ns et perdre des ex aequo."""
    if end <= start or limit < 2 or timeout <= 0:
        raise ValueError('Intervalle, limite ou timeout invalide')
    page = page or request_page
    result = []
    pending = [(start, end)]  # Intervalle utilisateur [start, end).
    requests = 0
    while pending:
        lo, hi = pending.pop()
        requests += 1
        if requests > 10000:
            raise ValueError('Trop de requêtes : réduire la période demandée')
        rows = page(base, query, lo, hi, limit, timeout)
        if len(rows) >= limit:
            if hi - lo <= 1:
                raise ValueError('Trop de logs au même timestamp : augmenter --limit ; export abandonné')
            mid = (lo + hi) // 2
            pending.extend([(mid, hi), (lo, mid)])
        else:
            result.extend(rows)
    return sorted(result, key=lambda item: item[0])


def read_export(path):
    labels = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('Common labels:'):
            labels = json.loads(line.split(':', 1)[1])
        elif not line.strip() or line.startswith(('Line limit:', 'Total bytes processed:')):
            continue
        else:
            yield line, labels.copy(), None


def write_rows(items, output):
    output = Path(output)
    # Pas de CSV partiel en cas d'erreur de parsing. Un flux d'autres types de logs
    # doit être filtré explicitement plutôt que silencieusement ignoré.
    rows = [parse_access(line, labels, ns) for line, labels, ns in items]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status': 'collected', 'rows': len(rows), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export')
    export.add_argument('--input', required=True)
    export.add_argument('--out', required=True)
    loki = sub.add_parser('loki')
    loki.add_argument('--url', default=os.environ.get('LOKI_URL', 'http://loki:3100'))
    loki.add_argument('--query', default='{container="phenix-waf-1"} |= " HTTP/"')
    loki.add_argument('--start', required=True)
    loki.add_argument('--end', required=True)
    loki.add_argument('--limit', type=int, default=1000)
    loki.add_argument('--timeout', type=float, default=5)
    loki.add_argument('--out', required=True)
    args = parser.parse_args()
    if Path(args.out).exists():
        parser.error('Le fichier de sortie existe déjà : choisir un nouveau nom')
    try:
        if args.command == 'export':
            items = read_export(args.input)
        else:
            if urlsplit(args.url).scheme not in ['http', 'https']:
                raise ValueError('URL HTTP(S) requise')
            logs = fetch_range(args.url, args.query, time_ns(args.start), time_ns(args.end), args.limit, args.timeout)
            items = ((line, labels, str(ns)) for ns, line, labels in logs)
        write_rows(items, args.out)
    except Exception as exc:
        # Pas de réponse HTTP ni d'URL complète imprimée, pour éviter d'exposer des secrets.
        parser.exit(1, f'Collecte impossible ({type(exc).__name__}). Vérifier connexion, accès, période et format WAF.\n')


if __name__ == '__main__':
    main()