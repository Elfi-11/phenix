"""Comparer deux modèles figés sur le même jeu V2, sans réentraînement."""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import sklearn

from detector.__main__ import FEATURES, evaluate, load_data, split_data


def compare(csv_path, v1_model, v2_dir, output):
    v2_dir, output = Path(v2_dir), Path(output)
    if output.exists():
        raise ValueError('La sortie existe déjà')
    report = json.loads((v2_dir/'metrics.json').read_text(encoding='utf-8'))
    if hashlib.sha256(Path(csv_path).read_bytes()).hexdigest() != report['metadata']['source_sha256']:
        raise ValueError('Le CSV ne correspond pas à l’expérience V2')
    protocol = report['metadata']['protocol_days']
    parts = split_data(load_data(csv_path, labelled=True), protocol['train'], protocol['calibration'], protocol['validation'])
    results = {}
    for name, path in [('V1', v1_model), ('V2', v2_dir/'model.joblib')]:
        # Artefacts de confiance uniquement : joblib utilise pickle.
        bundle = joblib.load(path)
        if bundle['metadata']['versions']['sklearn'] != sklearn.__version__:
            raise ValueError('Versions scikit-learn différentes')
        if bundle['metadata']['features'] != FEATURES:
            raise ValueError('Variables différentes')
        results[name] = {}
        for split in ['validation', 'test']:
            df = parts[split]
            scores = -bundle['model'].score_samples(df[FEATURES])
            results[name][split] = evaluate(df, scores, bundle['metadata']['threshold'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, result in results.items():
        d = result['test']
        print(name, 'test V2 :', d['true_positive'], '/', d['anomaly_minutes'], 'minutes détectées ;', d['false_positive'], 'minutes normales signalées')
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', required=True)
    p.add_argument('--v1-model', required=True)
    p.add_argument('--v2-dir', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    compare(a.csv, a.v1_model, a.v2_dir, a.out)


if __name__ == '__main__': main()
