"""Une collecte Loki, deux modèles figés, un flux commun d’alertes ML."""
import argparse
import json
import sys
import joblib
from detector.collect import fetch_range
from detector.live import detect as detect_sql
from detector.bruteforce import detect as detect_bruteforce


def detect(sql_bundle, brute_bundle, logs, end_ns):
    # Les deux modèles gardent leur préparation et leur seuil d’origine.
    # SQL : chaque ligne ; brute force : login par IP dans les 60 dernières secondes.
    sql_alerts = detect_sql(sql_bundle, logs)
    brute_alerts = detect_bruteforce(brute_bundle, logs, end_ns)

    # Unifier les champs de routage sans confondre les scores des deux modèles.
    # Le préfixe de l’identité distingue les familles même pour un même log source.
    alerts = []
    for kind, score_field, family in [('sql_injection', 'sql_score', sql_alerts),
                                      ('bruteforce', 'bruteforce_score', brute_alerts)]:
        for original in family:
            alert = dict(original)
            alert['detection_kind'] = kind
            alert['score'] = float(alert[score_field])
            alert['detection_id'] = kind + ':' + alert['detection_id']
            alerts.append(alert)
    alerts.sort(key=lambda a: (int(a['loki_timestamp_ns']), a['detection_id']))
    return {'scanned': len(logs), 'counts': {'sql_injection': len(sql_alerts),
             'bruteforce': len(brute_alerts)}, 'alerts': alerts}


def main():
    # Le conteneur ne reçoit que les deux artefacts montés en lecture seule.
    # Aucune modification des poids, aucun socket Docker et aucun secret métier.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sql-model', required=True)
    parser.add_argument('--brute-model', required=True)
    parser.add_argument('--start-ns', type=int, required=True)
    parser.add_argument('--end-ns', type=int, required=True)
    parser.add_argument('--url', default='http://loki:3100')
    parser.add_argument('--query', default='{container="phenix-waf-1"} |= " HTTP/"')
    args = parser.parse_args()
    try:
        # Charger seulement les modèles de confiance produits par l’équipe.
        sql_bundle = joblib.load(args.sql_model)
        brute_bundle = joblib.load(args.brute_model)
        # Inclure au moins la minute requise par le modèle temporel, sans
        # exécuter deux collectes qui pourraient retourner des observations différentes.
        start = max(0, min(args.start_ns, args.end_ns - 60 * 10**9))
        logs = fetch_range(args.url, args.query, start, args.end_ns, timeout=5)
        print(json.dumps(detect(sql_bundle, brute_bundle, logs, args.end_ns), ensure_ascii=False))
    except Exception as exc:
        # Un modèle incompatible ou un parsing en échec invalide tout le cycle.
        # Le moteur conserve alors son curseur plutôt que déclarer un faux succès.
        print(f'Cycle ML commun impossible : {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
