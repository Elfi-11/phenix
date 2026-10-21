"""Un cycle Loki -> modèle SQL figé -> alertes JSON pour le moteur hôte."""
import argparse
import hashlib
import json
import sys
import joblib
import pandas as pd
import sklearn
from detector.collect import fetch_range, parse_access
from detector.sql import SCHEMA, texts


def detect(bundle, logs):
    # Vérifier que l’artefact correspond au schéma et à la bibliothèque attendus.
    meta,model=bundle['metadata'],bundle['model']
    if meta.get('feature_schema')!=SCHEMA or meta['versions']['sklearn']!=sklearn.__version__:
        raise ValueError('Modèle SQL ou version scikit-learn incompatible')
    if not logs:return []
    # Une ligne non conforme invalide le cycle, sans avancer silencieusement le curseur.
    frame=pd.DataFrame([parse_access(line,labels,str(ns)) for ns,line,labels in logs])
    # Appliquer exactement la préparation du texte utilisée à l’entraînement.
    # Le modèle reste figé : ce cycle ne réentraîne aucun paramètre.
    scores=model.predict_proba(texts(frame))[:,1]
    alerts=[]
    # Le seuil enregistré dans le modèle décide de l’alerte. Son identité stable
    # permet au moteur de reconnaître un log relu lors du cycle suivant.
    for i,score in enumerate(scores):
        if score<=meta['threshold']:continue
        ns,line,labels=logs[i]
        key=json.dumps([str(ns),labels,line],sort_keys=True,ensure_ascii=False)
        # Transmettre les informations utiles à la remédiation, sans requête
        # SQL brute ni jeton d’authentification dans le message d’alerte.
        alerts.append({
            'detection_id':hashlib.sha256(key.encode()).hexdigest(),
            'observed_at':frame.iloc[i].observed_at,'loki_timestamp_ns':str(ns),
            'event_type':'ML_ANOMALY_DETECTED','severity':'CRITICAL','source':'ML',
            'target_service':'backend','ip':frame.iloc[i].client_ip,'peer_ip':frame.iloc[i].peer_ip,
            'sql_score':float(score),'threshold':float(meta['threshold']),
            'description':f"Suspicion d’injection SQL détectée par ML depuis {frame.iloc[i].client_ip} (score={score:.4f}).",
        })
    return alerts


# Exécuter une seule fenêtre Loki et retourner un JSON lisible par le moteur.
# Les erreurs partent sur stderr avec un code non nul : pas de faux succès.
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start-ns',type=int,required=True);p.add_argument('--end-ns',type=int,required=True)
    p.add_argument('--model',required=True);p.add_argument('--url',default='http://loki:3100')
    p.add_argument('--query',default='{container="phenix-waf-1"} |= " HTTP/"')
    a=p.parse_args()
    try:
        # Artefact local de confiance, monté en lecture seule par le moteur.
        bundle=joblib.load(a.model)
        logs=fetch_range(a.url,a.query,a.start_ns,a.end_ns,timeout=5)
        alerts=detect(bundle,logs)
        print(json.dumps({'scanned':len(logs),'alerts':alerts},ensure_ascii=False))
    except Exception as exc:
        print(f'Cycle Loki/ML impossible : {type(exc).__name__}: {exc}',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':main()
