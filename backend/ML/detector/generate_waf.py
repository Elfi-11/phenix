"""Génère hors réseau des accès WAF et leurs annotations, sans exécuter de requête."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
from urllib.parse import quote, quote_plus

from detector.collect import FIELDS, parse_access, time_ns

# Les exemples sont des tentatives synthétiques : leur succès SQL n'est pas affirmé.
ATTACKS = {
    'boolean': ["SUCCESS' OR 1=1 --", "FAILED' AND 2=2 --", "' OR 'a'='a' --"],
    'union': ["SUCCESS' UNION SELECT NULL --", "FAILED' UNION ALL SELECT NULL,NULL --"],
    'comment': ["SUCCESS' --", "FAILED' /*", "PENDING' --"],
    'boolean_nested': ["SUCCESS' OR (3=3) --", "FAILED' AND (7>2) --"],
}
NORMAL_SEARCH = ['SUCCESS', 'FAILED', 'PENDING', 'REJECTED_FRAUD', 'commande 2026',
                 "O'Reilly", 'Union des clients', 'select a payment', 'A+B', '50% remise',
                 'or and', 'benchmark résultats', 'été à Toulouse', '(commande)', 'a=b', '']
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
PROTOCOL = [('train', 120), ('calibration', 40), ('validation', 40), ('test', 60)]
SCENARIOS = {'train': [], 'calibration': [], 'validation': ['boolean', 'union'],
             'test': ['comment', 'boolean_nested']}


def format_time(stamp):
    return f'{stamp.day:02d}/{MONTHS[stamp.month-1]}/{stamp.year:04d}:{stamp:%H:%M:%S} +0000'


def generate(out, seed=20261021, requests_per_session=50):
    if not isinstance(requests_per_session, int) or requests_per_session < 10:
        raise ValueError('Au moins dix requêtes par session')
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choisir un dossier nouveau ou vide')
    out.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)
    labels = {'container': 'phenix-waf-1', 'service': 'waf', 'service_name': 'waf'}
    counts = {}
    with (out/'waf.log').open('w', encoding='utf-8') as raw, \
         (out/'waf.csv').open('w', encoding='utf-8', newline='') as parsed, \
         (out/'annotations.csv').open('w', encoding='utf-8', newline='') as truth:
        writer = csv.DictWriter(parsed, fieldnames=FIELDS)
        writer.writeheader()
        ann = csv.DictWriter(truth, fieldnames=['loki_timestamp_ns', 'split', 'session_id', 'scenario', 'is_attack'])
        ann.writeheader()
        position = 0
        for split_index, (split, sessions) in enumerate(PROTOCOL):
            # Flux aléatoire indépendant par partie, sans partage de session.
            rng = random.Random(seed + split_index * 100003)
            stats = {'sessions': sessions, 'requests': 0, 'attack_requests': 0}
            for session in range(sessions):
                session_id = f'{split}-{session:04d}'
                start = base + timedelta(minutes=position*15)
                position += 1
                client = f'192.0.2.{rng.randint(1, 254)}'
                # L'adresse et l'agent ne codent pas l'étiquette ; valeurs de documentation.
                agent = rng.choice(['Mozilla/5.0 WorkshopBrowser/1.0', 'python-requests/2.32', 'curl/8.0'])
                families = SCENARIOS[split]
                scenario = families[(session // 2) % len(families)] if families and session % 2 == 0 else 'normal'
                # Fenêtres de recherche normales et suspectes ; rythme variable dans les deux cas.
                pace = rng.choice([1, 2, 5, 8])
                for j in range(requests_per_session):
                    stamp = start + timedelta(seconds=j * pace)
                    attack = scenario != 'normal' and requests_per_session//3 <= j < 2*requests_per_session//3
                    method = 'GET'
                    if attack:
                        value = rng.choice(ATTACKS[scenario])
                        route = '/api/attackme/search'
                    else:
                        route = rng.choices(['/api/attackme/search', '/docs', '/openapi.json', '/api/accounts/me', '/api/auth/login', '/api/transactions'], weights=[55, 6, 4, 15, 10, 10])[0]
                        value = rng.choice(NORMAL_SEARCH)
                        if route in ['/api/auth/login', '/api/transactions']:
                            method = 'POST'
                    if route == '/api/attackme/search':
                        encoding = rng.choice(['space', 'plus', 'double'])
                        value = quote_plus(value, safe='') if encoding == 'plus' else quote(value, safe='')
                        if encoding == 'double':
                            value = quote(value, safe='')
                        target = route + '?q=' + value
                    else:
                        target = route
                    # Même loi de statuts et tailles pour les deux classes : pas de raccourci 403=attaque.
                    status = rng.choices([200, 401, 403, 404, 500], weights=[88, 4, 3, 3, 2])[0]
                    size = rng.choice([2, 24, 80, 206, 548, 934, 13657])
                    line = f'172.26.0.1 - - [{format_time(stamp)}] "{method} {target} HTTP/1.1" {status} {size} "-" "{agent}" "{client}"'
                    ns = str(time_ns(stamp.isoformat()) + j + 1)
                    raw.write(line + '\n')
                    writer.writerow(parse_access(line, labels, ns))
                    ann.writerow({'loki_timestamp_ns': ns, 'split': split, 'session_id': session_id,
                                  'scenario': scenario, 'is_attack': int(attack)})
                    stats['requests'] += 1
                    stats['attack_requests'] += int(attack)
            counts[split] = stats
    manifest = {
        'origin': 'synthetic', 'schema_version': 'waf-v1', 'seed': seed,
        'requests_per_session': requests_per_session, 'splits': counts,
        'annotation_key': 'loki_timestamp_ns', 'timestamp_note': 'Horodatages Loki simulés, pas une collecte réelle',
        'training_protocol': 'train et calibration normaux ; validation/test avec familles distinctes',
        'limits': ['Hypothèses non estimées sur un historique réel',
                   'Distributions de statut et taille simplifiées et indépendantes du scénario',
                   'Exemples SQL non exécutés, aucune preuve de réussite de l’injection',
                   'Aucune charge SQL dans le corps POST : non observable dans le format accès',
                   'Ne pas utiliser IP, session_id, split, scenario, date ou nom de route comme preuve d’attaque',
                   'Ne pas sélectionner un modèle sur le test puis présenter ce test comme indépendant'],
        'sha256': {name: hashlib.sha256((out/name).read_bytes()).hexdigest()
                   for name in ['waf.log', 'waf.csv', 'annotations.csv']},
    }
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seed', type=int, default=20261021)
    parser.add_argument('--requests-per-session', type=int, default=50)
    args = parser.parse_args()
    result = generate(args.out, args.seed, args.requests_per_session)
    print(json.dumps({'origin': result['origin'], 'splits': result['splits']}, indent=2))


if __name__ == '__main__':
    main()