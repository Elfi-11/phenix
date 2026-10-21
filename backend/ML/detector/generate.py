"""Générateur synthétique V2, distinct du générateur inconnu du CSV V1.

Les plages sont des hypothèses de simulation, pas des mesures de Phenix.
Les scénarios désignent des symptômes, pas des attaques ou des remèdes prouvés.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROTOCOL = [("train", 10), ("calibration", 7), ("validation", 5), ("test", 6)]
COLUMNS = ["req_per_sec", "latency_ms", "error_rate_pct", "cpu_usage_pct", "auth_failures_per_min"]


def generate(seed=20261021):
    frames, events = [], []
    # Flux aléatoires indépendants par partie : pas de fenêtre partagée.
    seeds = np.random.SeedSequence(seed).spawn(len(PROTOCOL))
    start = pd.Timestamp("2026-11-01")  # Dates fictives ; fuseau non attribué.
    for (split, days), child_seed in zip(PROTOCOL, seeds):
        rng = np.random.default_rng(child_seed)
        n = days * 1440
        dates = pd.date_range(start, periods=n, freq="min")
        minutes = np.arange(n)
        hour = (minutes % 1440) / 60
        daily = rng.uniform(.75, 1.25, days).repeat(1440)
        weekday_factor = np.where(dates.dayofweek >= 5, .82, 1.0)
        # Activité diurne, bruit corrélé et diversité des journées normales.
        smooth_noise = np.convolve(rng.normal(0, 2, n + 14), np.ones(15) / 15, mode='valid')
        req = (12 + 24 * np.exp(-((hour - 13) / 4.5) ** 2) + 15 * np.exp(-((hour - 20) / 2.5) ** 2)) * daily * weekday_factor
        req += smooth_noise + rng.normal(0, 2, n)
        # Pics légitimes longs : plusieurs niveaux, tous laissés annotés normaux.
        for day in range(days):
            for period in [rng.integers(7 * 60, 11 * 60), rng.integers(17 * 60, 21 * 60)]:
                duration = int(rng.integers(45, 150))
                begin = int(day * 1440 + period)
                end = min(begin + duration, (day + 1) * 1440)
                req[begin:end] += rng.uniform(25, 85) * np.sin(np.linspace(.1, np.pi - .1, end - begin))
        req = np.maximum(req, 1.5)
        cpu = np.clip(8 + .62 * req + rng.normal(0, 4, n), 2, 96)
        latency = np.maximum(12 + .26 * req + .004 * np.maximum(req - 65, 0) ** 2 + rng.normal(0, 2.5, n), 5)
        errors = np.clip(.45 + .009 * req + rng.normal(0, .25, n), 0, 4)
        auth = rng.poisson(.3 + req * .05)
        df = pd.DataFrame({"timestamp": dates, "req_per_sec": req, "latency_ms": latency,
                           "error_rate_pct": errors, "cpu_usage_pct": cpu,
                           "auth_failures_per_min": auth,
                           "balance_integrity_status": np.ones(n, dtype=int),
                           "is_anomaly": np.zeros(n, dtype=int)})
        # Pas d'incident dans le train. Les trois autres parties ont leur propre scénario.
        schedule = {"train": [], "calibration": [(0, "traffic_stress"), (2, "auth_burst"), (5, "latency_drift")],
                    "validation": [(0, "traffic_stress"), (1, "auth_burst"), (2, "latency_drift"), (4, "error_burst")],
                    "test": [(0, "auth_burst"), (1, "traffic_stress"), (2, "latency_drift"), (4, "error_burst"), (5, "traffic_stress")]}
        for event_number, (day, kind) in enumerate(schedule[split]):
            length = int(rng.integers(20, 61))
            begin = int(day * 1440 + rng.integers(2 * 60, 22 * 60))
            idx = np.arange(begin, begin + length)
            if kind == "traffic_stress":
                df.loc[idx, "req_per_sec"] += rng.uniform(65, 170)
                df.loc[idx, "cpu_usage_pct"] = np.clip(df.loc[idx, "cpu_usage_pct"] + rng.uniform(20, 45), 0, 100)
                df.loc[idx, "latency_ms"] += np.linspace(10, rng.uniform(80, 250), length)
                df.loc[idx, "error_rate_pct"] += rng.uniform(2, 12)
            elif kind == "auth_burst":
                # Anomalie concentrée sur une variable, moins facile qu'un décalage global.
                df.loc[idx, "auth_failures_per_min"] += rng.poisson(rng.uniform(15, 45), length)
            elif kind == "latency_drift":
                df.loc[idx, "latency_ms"] += np.linspace(0, rng.uniform(70, 160), length)
            else:
                df.loc[idx, "error_rate_pct"] += rng.uniform(4, 14)
            df.loc[idx, "is_anomaly"] = 1
            events.append({"event_id": f"{split}-{event_number + 1}", "split": split, "symptom": kind,
                           "start": str(df.loc[begin, "timestamp"]), "end": str(df.loc[begin + length - 1, "timestamp"]),
                           "minutes": length, "target_service": None, "expected_remediation": None})
        for col in COLUMNS[:-1]:
            df[col] = df[col].round(2)
        frames.append(df)
        start = dates[-1] + pd.Timedelta(minutes=1)
    return pd.concat(frames, ignore_index=True), events


def main():
    parser = argparse.ArgumentParser(description="Télémétrie synthétique V2 — ne prouve aucun comportement réel")
    parser.add_argument('--out', required=True)
    parser.add_argument('--seed', type=int, default=20261021)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        parser.error('Le dossier de sortie doit être vide ou nouveau')
    out.mkdir(parents=True, exist_ok=True)
    df, events = generate(args.seed)
    p = out / 'telemetry.csv'
    df.to_csv(p, index=False)
    manifest = {"origin": "synthetic", "generator": "detector.generate V2", "seed": args.seed,
                "protocol_days": dict(PROTOCOL), "rows": len(df), "incident_episodes": events,
                "source_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "definitions": {"timestamp": "dates fictives, sans fuseau ; une ligne par minute",
                    "req_per_sec": "débit moyen de la minute simulée",
                    "latency_ms": "latence moyenne simulée sur la minute, pas un p95",
                    "error_rate_pct": "proportion simulée de réponses HTTP 5xx, en pourcentage",
                    "cpu_usage_pct": "utilisation simulée d'une capacité CPU normalisée à 100 % ; périmètre réel à définir",
                    "auth_failures_per_min": "nombre simulé d'échecs d'authentification dans la minute",
                    "balance_integrity_status": "champ de compatibilité constant à 1, non exploité",
                    "is_anomaly": "annotation du scénario, jamais variable d'entrée"}}
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({"rows": len(df), "episodes": len(events), "out": str(out)}))


if __name__ == '__main__': main()
