"""Essai contextuel : relations apprises sur le trafic normal, validation seule."""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from detector.__main__ import FEATURES, load_data, split_data, evaluate


class ContextDetector:
    """Mesure l'écart aux métriques attendues pour un volume de trafic donné."""
    def fit(self, frame):
        # Aucun horodatage, label ou scénario n'entre dans la régression.
        self.regressor = make_pipeline(PolynomialFeatures(2, include_bias=False),
                                      StandardScaler(), Ridge(alpha=1.0))
        self.regressor.fit(frame[[FEATURES[0]]], frame[FEATURES[1:]])
        residual = frame[FEATURES[1:]].to_numpy() - self.regressor.predict(frame[[FEATURES[0]]])
        self.center = np.median(residual, axis=0)
        self.scale = np.maximum(np.median(np.abs(residual - self.center), axis=0) * 1.4826, 1e-6)
        self.traffic_center = float(frame[FEATURES[0]].median())
        self.traffic_scale = max(float(np.median(np.abs(frame[FEATURES[0]] - self.traffic_center))) * 1.4826, 1e-6)
        return self

    def components(self, frame):
        residual = frame[FEATURES[1:]].to_numpy() - self.regressor.predict(frame[[FEATURES[0]]])
        deviations = np.abs((residual - self.center) / self.scale)
        traffic = np.abs((frame[FEATURES[0]].to_numpy() - self.traffic_center) / self.traffic_scale)
        return np.column_stack([traffic, deviations])

    def score_samples(self, frame):
        # Score sans probabilité ni attribution d'une cause d'incident.
        return self.components(frame).max(axis=1)


def run(csv, out):
    frame = load_data(csv, labelled=True)
    # Le test déjà consulté reste exclu de cette comparaison exploratoire.
    parts = split_data(frame, 10, 7, 5)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choisir un dossier vide ou nouveau')
    model = ContextDetector().fit(parts['train'])
    normal = parts['calibration'].loc[parts['calibration'].is_anomaly == 0]
    if len(normal) < 100:
        raise ValueError('Calibration normale insuffisante')
    threshold = float(np.quantile(model.score_samples(normal), .995))
    metadata = {'model': 'ContextResidual', 'features': FEATURES, 'threshold': threshold,
                'quantile': .995, 'source_sha256': hashlib.sha256(Path(csv).read_bytes()).hexdigest(),
                'protocol_days': {'train': 10, 'calibration': 7, 'validation': 5},
                'scope': 'exploratory_validation_only', 'data_origin': 'synthetic'}
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': model, 'metadata': metadata}, out / 'model.joblib')
    reports = {}
    for name in ['train', 'calibration', 'validation']:
        part = parts[name]
        scores = model.score_samples(part)
        reports[name] = evaluate(part, scores, threshold)
        pred = part[['timestamp', 'is_anomaly']].copy()
        pred['anomaly_score'] = scores
        pred['predicted_anomaly'] = (scores > threshold).astype(int)
        pred.to_csv(out / f'{name}_predictions.csv', index=False)
    report = {'metadata': metadata, 'splits': reports}
    (out / 'metrics.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(reports['validation'], indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    run(args.csv, args.out)
