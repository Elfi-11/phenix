"""Détecteur expérimental de rafales de login : apprentissage synthétique, lecture WAF."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import sklearn
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_score, recall_score
from detector.collect import fetch_range, parse_access

# Le même calcul est employé en entraînement et en lecture réelle. Ni IP,
# ni mot de passe, ni texte SQL ne sont des variables d’apprentissage.
FEATURES = ['attempts_60s', 'failures_60s', 'failure_ratio', 'failures_per_active_second']
SCHEMA = 'waf-login-window-v1'
NS = 10**9


def features(stamps, statuses):
    """Résumer les POST login d’une IP dans une fenêtre de 60 secondes."""
    count = len(statuses)
    failures = sum(int(s) == 401 for s in statuses)
    duration = max(1.0, (max(stamps) - min(stamps)) / NS) if stamps else 1.0
    return [count, failures, failures / max(1, count), failures / duration]


def synthetic(seed, size):
    """Produire des fenêtres indépendantes avec des cas ambigus communs aux classes.

    Les étiquettes viennent du scénario généré, pas d’un seuil appliqué au modèle.
    Les attaques lentes et les utilisateurs faisant plusieurs erreurs se recouvrent.
    """
    rng = np.random.default_rng(seed)
    x, y = [], []
    for _ in range(size):
        attack = bool(rng.random() < .25)
        if attack:
            count = int(rng.integers(4, 90))
            span = rng.uniform(2, 59)
            failure_probability = rng.uniform(.78, 1)
        else:
            # Les usages chargés existent aussi hors attaque : ne pas apprendre
            # uniquement une règle de volume total.
            count = int(rng.integers(1, 9) if rng.random() < .9 else rng.integers(9, 60))
            span = rng.uniform(1, 59)
            failure_probability = rng.uniform(0, .45)
            if rng.random() < .08:
                count = int(rng.integers(2, 12))
                failure_probability = rng.uniform(.65, 1)
        stamps = sorted(int(t * NS) for t in rng.uniform(0, span, count))
        statuses = [401 if rng.random() < failure_probability else 200 for _ in stamps]
        x.append(features(stamps, statuses)); y.append(int(attack))
    return np.asarray(x), np.asarray(y)


def train(out):
    """Apprendre sur train, choisir le seuil sur calibration, évaluer le test une fois."""
    out = Path(out)
    if out.exists():
        raise ValueError('Dossier déjà présent : choisir un nouveau dossier de sortie')
    x, y = synthetic(81, 6000)
    cx, cy = synthetic(82, 2000)
    tx, ty = synthetic(83, 2000)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced', random_state=81))
    model.fit(x, y)
    scores = model.predict_proba(cx)[:, 1]
    # Choisir le meilleur rappel respectant au plus 1 % de faux positifs
    # sur calibration uniquement ; le jeu de test n’influence pas ce choix.
    candidates = np.unique(np.r_[scores, 1.0])
    eligible = [float(t) for t in candidates if np.mean(scores[cy == 0] > t) <= .01]
    threshold = max(eligible, key=lambda t: (np.mean(scores[cy == 1] > t), -np.sum(scores[cy == 0] > t), t))
    predicted = model.predict_proba(tx)[:, 1] > threshold
    tn, fp, fn, tp = confusion_matrix(ty, predicted, labels=[0, 1]).ravel()
    metrics = {'origin': 'synthetic', 'unit': 'one IP / 60-second window', 'train_rows': len(y),
               'calibration_rows': len(cy), 'test_rows': len(ty), 'threshold': threshold,
               'test': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp),
                        'precision': float(precision_score(ty, predicted, zero_division=0)),
                        'recall': float(recall_score(ty, predicted, zero_division=0))},
               'limits': 'Synthetic independent windows; no validation on real traffic; distributed and slow attacks may be missed.'}
    out.mkdir(parents=True)
    joblib.dump({'model': model, 'schema': SCHEMA, 'features': FEATURES, 'threshold': threshold,
                 'sklearn': sklearn.__version__}, out / 'model.joblib')
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps(metrics, indent=2))


def detect(bundle, logs, end_ns):
    """Analyser exclusivement les login dans [fin - 60 s, fin[ ; une alerte par IP."""
    if bundle['schema'] != SCHEMA or bundle['features'] != FEATURES or bundle['sklearn'] != sklearn.__version__:
        raise ValueError('Artefact brute force incompatible')
    groups = {}
    for ns, line, labels in logs:
        stamp = int(ns)
        if not end_ns - 60 * NS <= stamp < end_ns:
            continue
        row = parse_access(line, labels, str(ns))
        if row['method'] != 'POST' or row['path'] != '/api/auth/login':
            continue
        groups.setdefault(row['client_ip'], []).append((stamp, row))
    alerts = []
    for ip, rows in groups.items():
        rows.sort(key=lambda item: item[0])
        vector = features([ns for ns, _ in rows], [r['status'] for _, r in rows])
        score = float(bundle['model'].predict_proba([vector])[0, 1])
        if score <= bundle['threshold']:
            continue
        # Identité liée à la dernière requête : la même fenêtre relue sans
        # nouveau login ne recrée pas une détection.
        stamp, latest = rows[-1]
        key = hashlib.sha256(f'bruteforce:{ip}:{stamp}'.encode()).hexdigest()
        alerts.append({'detection_id': key, 'loki_timestamp_ns': str(stamp),
                       'observed_at': latest['observed_at'], 'ip': ip, 'peer_ip': latest['peer_ip'],
                       'event_type': 'ML_ANOMALY_DETECTED', 'severity': 'WARNING', 'source': 'ML',
                       'target_service': 'backend', 'bruteforce_score': score, 'threshold': float(bundle['threshold']),
                       'description': f'Suspicion de brute force ML depuis {ip} : {vector[1]} échecs / {vector[0]} connexions en 60 s (score={score:.4f}).'})
    return alerts


def main():
    # L’entraînement est explicite ; le mode live charge le modèle figé et
    # retourne un seul JSON. Toute erreur empêche le succès du cycle appelant.
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('train'); p.add_argument('--out', required=True)
    p = sub.add_parser('live'); p.add_argument('--model', required=True)
    p.add_argument('--start-ns', type=int, required=True); p.add_argument('--end-ns', type=int, required=True)
    p.add_argument('--url', default='http://loki:3100')
    p.add_argument('--query', default='{container="phenix-waf-1"} |= " HTTP/"')
    args = parser.parse_args()
    try:
        if args.command == 'train':
            train(args.out)
        else:
            # Joblib doit charger uniquement notre propre artefact local de confiance.
            bundle = joblib.load(args.model)
            logs = fetch_range(args.url, args.query, max(0, args.end_ns - 60 * NS), args.end_ns, timeout=5)
            print(json.dumps({'scanned': len(logs), 'alerts': detect(bundle, logs, args.end_ns)}, ensure_ascii=False))
    except Exception as exc:
        print(f'Brute force : {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
