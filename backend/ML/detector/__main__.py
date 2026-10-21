"""CLI : entraînement chronologique et scoring de CSV, hors supervision en direct."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support

# Contrat d'entrée V1. Ni la date ni l'étiquette ne sont données au modèle.
# L'intégrité métier est exclue : définition inconnue et constante dans le train normal.
FEATURES = ["req_per_sec", "latency_ms", "error_rate_pct", "cpu_usage_pct", "auth_failures_per_min"]


def load_data(path, labelled=False):
    df = pd.read_csv(path)
    required = ["timestamp", *FEATURES] + (["is_anomaly"] if labelled else [])
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"Colonnes absentes : {missing}")
    if df.empty:
        raise ValueError("CSV vide")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    if df["timestamp"].isna().any() or df["timestamp"].duplicated().any():
        raise ValueError("Horodatages manquants ou dupliqués")
    df = df.sort_values("timestamp").reset_index(drop=True)
    # Pas d'imputation silencieuse d'une mesure absente en fonctionnement normal.
    for col in FEATURES:
        df[col] = pd.to_numeric(df[col], errors="raise")
        if not np.isfinite(df[col]).all() or (df[col] < 0).any():
            raise ValueError(f"Valeur absente, infinie ou négative : {col}")
    for col in ["error_rate_pct", "cpu_usage_pct"]:
        if (df[col] > 100).any():
            raise ValueError(f"Pourcentage hors [0, 100] : {col}")
    if not (df.auth_failures_per_min % 1 == 0).all():
        raise ValueError("Les échecs d'authentification doivent être des comptes entiers")
    if len(df) > 1 and not df.timestamp.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("La V1 attend une observation toutes les minutes, sans trou")
    if labelled and not df.is_anomaly.isin([0, 1]).all():
        raise ValueError("is_anomaly doit valoir 0 ou 1")
    return df


def split_data(df):
    """Protocole fixé : 4 jours train, 4 calibration, 3 validation, reste test."""
    start = df.timestamp.iloc[0]
    borders = [start + pd.Timedelta(days=n) for n in [4, 8, 11]]
    parts = {
        "train": df[df.timestamp < borders[0]].copy(),
        "calibration": df[(df.timestamp >= borders[0]) & (df.timestamp < borders[1])].copy(),
        "validation": df[(df.timestamp >= borders[1]) & (df.timestamp < borders[2])].copy(),
        "test": df[df.timestamp >= borders[2]].copy(),
    }
    if any(part.empty for part in parts.values()):
        raise ValueError("Le protocole attend plus de 11 jours de données")
    if parts["train"].is_anomaly.ne(0).any():
        raise ValueError("Le train doit être une période identifiée comme normale")
    # Ne pas partager un incident continu entre deux parties.
    for border in borders:
        before, after = df[df.timestamp < border], df[df.timestamp >= border]
        if before.is_anomaly.iloc[-1] == 1 and after.is_anomaly.iloc[0] == 1:
            raise ValueError("Une frontière coupe un épisode d'anomalie")
    return parts


def evaluate(df, scores, threshold):
    pred = (scores > threshold).astype(int)
    y = df.is_anomaly.to_numpy(dtype=int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    episodes = []
    # Évaluation par incident sans ajuster artificiellement les prédictions.
    for _, block in df.groupby(df.is_anomaly.ne(df.is_anomaly.shift()).cumsum()):
        if block.is_anomaly.iloc[0] != 1:
            continue
        indices = df.index.get_indexer(block.index)
        hits = np.flatnonzero(pred[indices])
        episodes.append({"start": str(block.timestamp.iloc[0]), "end": str(block.timestamp.iloc[-1]),
                         "minutes": len(block), "detected": bool(len(hits)),
                         "delay_minutes": int(hits[0]) if len(hits) else None})
    false_episodes = int(np.sum((pred == 1) & (y == 0) & ~np.r_[False, ((pred == 1) & (y == 0))[:-1]]))
    return {"rows": len(df), "start": str(df.timestamp.iloc[0]), "end": str(df.timestamp.iloc[-1]),
            "anomaly_minutes": int(y.sum()), "true_negative": int(tn), "false_positive": int(fp),
            "false_negative": int(fn), "true_positive": int(tp),
            "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "average_precision": float(average_precision_score(y, scores)) if len(set(y)) == 2 else None,
            "false_positive_rate": float(fp / (tn + fp)) if tn + fp else None,
            "false_alert_minutes_per_observed_day": float(fp / (len(df) / 1440)),
            "false_alert_runs": false_episodes, "episodes": episodes}


def train(csv_path, out, quantile=0.995):
    if not 0 < quantile < 1:
        raise ValueError("Le quantile doit être entre 0 et 1 exclus")
    df = load_data(csv_path, labelled=True)
    parts = split_data(df)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Le dossier de sortie doit être vide ou nouveau pour préserver les essais")
    out.mkdir(parents=True, exist_ok=True)
    # Algorithme non supervisé ; période normale choisie grâce aux annotations.
    model = IsolationForest(n_estimators=200, max_samples=256, contamination="auto", random_state=42, n_jobs=1)
    t0 = time.perf_counter()
    model.fit(parts["train"][FEATURES])
    training_seconds = time.perf_counter() - t0
    normal_cal = parts["calibration"].loc[parts["calibration"].is_anomaly == 0, FEATURES]
    if len(normal_cal) < 100:
        raise ValueError("Pas assez de données normales pour calibrer le seuil")
    # Signe inversé : un score élevé représente une observation plus inhabituelle.
    threshold = float(np.quantile(-model.score_samples(normal_cal), quantile))
    metadata = {"model": "IsolationForest", "features": FEATURES, "threshold": threshold,
                "quantile": quantile, "seed": 42, "n_estimators": 200, "max_samples": 256,
                "source_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
                "data_origin": "synthetic", "training_seconds": training_seconds,
                "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                             "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__}}
    joblib.dump({"model": model, "metadata": metadata}, out / "model.joblib")
    reports = {}
    for name, part in parts.items():
        scores = -model.score_samples(part[FEATURES])
        reports[name] = evaluate(part, scores, threshold)
        predictions = part[["timestamp", "is_anomaly"]].copy()
        predictions["anomaly_score"] = scores
        predictions["predicted_anomaly"] = (scores > threshold).astype(int)
        predictions.to_csv(out / f"{name}_predictions.csv", index=False)
    report = {"metadata": metadata, "splits": reports,
              "constant_training_features": [c for c in FEATURES if parts['train'][c].nunique() == 1]}
    (out / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": "trained", "output": str(out), "test": reports["test"]}, indent=2))
    return report


def score(csv_path, model_path, out):
    # Charger uniquement un artefact local de confiance : joblib utilise pickle.
    bundle = joblib.load(model_path)
    meta, model = bundle["metadata"], bundle["model"]
    if meta["versions"]["sklearn"] != sklearn.__version__:
        raise ValueError("Version scikit-learn différente : utiliser la version d'entraînement")
    if meta["features"] != FEATURES:
        raise ValueError("Contrat de variables différent")
    df = load_data(csv_path)
    scores = -model.score_samples(df[FEATURES])
    result = df[["timestamp"]].copy()
    result["anomaly_score"] = scores
    result["predicted_anomaly"] = (scores > meta["threshold"]).astype(int)
    out = Path(out)
    if out.exists() or out.with_suffix(".alerts.jsonl").exists():
        raise ValueError("Choisir un nouveau chemin de sortie")
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    with out.with_suffix(".alerts.jsonl").open("w", encoding="utf-8") as f:
        for row in result[result.predicted_anomaly == 1].itertuples(index=False):
            event = {"event_type": "ML_ANOMALY_DETECTED", "observed_at": str(row.timestamp),
                     "source": "ML", "target_service": None, "anomaly_score": row.anomaly_score,
                     "threshold": meta["threshold"], "model": "IsolationForest",
                     "mode": "observation", "recommended_action": None}
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "scored", "rows": len(result), "alerts": int(result.predicted_anomaly.sum()), "output": str(out)}))


def main():
    parser = argparse.ArgumentParser(description="Détecteur expérimental Phenix — aucune remédiation")
    sub = parser.add_subparsers(dest="command", required=True)
    tr = sub.add_parser("train")
    tr.add_argument("--csv", required=True)
    tr.add_argument("--out", required=True)
    tr.add_argument("--quantile", type=float, default=0.995)
    sc = sub.add_parser("score")
    sc.add_argument("--csv", required=True)
    sc.add_argument("--model", required=True)
    sc.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "train":
            train(args.csv, args.out, args.quantile)
        else:
            score(args.csv, args.model, args.out)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Erreur : {exc}\n")


if __name__ == "__main__":
    main()