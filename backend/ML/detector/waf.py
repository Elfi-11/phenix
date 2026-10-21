"""Détecteur exploratoire d'URL atypiques : apprentissage normal, validation séparée."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import re
import time
from urllib.parse import unquote_plus

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix

SCHEMA = 'waf-query-shape-v1'
FEATURES = ['raw_length', 'decoded_length', 'percent_count', 'plus_count',
            'decode_reduction', 'second_decode_reduction', 'parameter_count',
            'quote_count', 'space_count', 'equals_count', 'dash_count', 'slash_count',
            'parenthesis_count', 'semicolon_count', 'digit_ratio', 'punctuation_ratio',
            'non_ascii_ratio', 'token_count', 'longest_token', 'character_entropy']


def query_features(value):
    """Forme du paramètre seulement : aucun mot-clé SQL, IP, route ou statut."""
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError('Paramètres absents ou trop longs pour ce contrat')
    once = unquote_plus(value)
    decoded = unquote_plus(once)
    size = max(len(decoded), 1)
    tokens = re.findall(r'\w+', decoded, flags=re.UNICODE)
    frequencies = np.array(list(Counter(decoded).values()), dtype=float)
    entropy = float(-(frequencies / size * np.log2(frequencies / size)).sum()) if len(frequencies) else 0.0
    values = [len(value), len(decoded), value.count('%'), value.count('+'),
              len(value)-len(once), len(once)-len(decoded), value.count('&')+1 if value else 0,
              decoded.count("'")+decoded.count('"'), sum(c.isspace() for c in decoded),
              decoded.count('='), decoded.count('-'), decoded.count('/'),
              decoded.count('(')+decoded.count(')'), decoded.count(';'),
              sum(c.isdigit() for c in decoded)/size,
              sum(not c.isalnum() and not c.isspace() for c in decoded)/size,
              sum(ord(c)>127 for c in decoded)/size, len(tokens),
              max(map(len, tokens), default=0), entropy]
    return dict(zip(FEATURES, values))


def extract_features(frame):
    if 'query' not in frame:
        raise ValueError('Colonne query absente : utiliser le CSV du collecteur')
    return pd.DataFrame([query_features(v) for v in frame['query']], columns=FEATURES, index=frame.index)


def read_requests(path):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {'observed_at', 'loki_timestamp_ns', 'client_ip', 'request_target', 'query'}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError('CSV vide ou contrat de collecte incomplet')
    for text in frame['observed_at']:
        # UTC forcé seulement après vérification d'un fuseau explicite.
        if pd.Timestamp(text).tzinfo is None:
            raise ValueError('Horodatage sans fuseau')
    stamps = pd.to_datetime(frame['observed_at'], utc=True)
    if stamps.isna().any():
        raise ValueError('Horodatage absent')
    if any(target.partition('?')[2] != query for target, query in zip(frame.request_target, frame['query'])):
        raise ValueError('Désaccord entre request_target et query')
    return frame


def load_dataset(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('origin') != 'synthetic' or manifest.get('schema_version') != 'waf-v1':
        raise ValueError('Ce protocole attend le générateur synthétique WAF v1')
    for name in ['waf.csv', 'annotations.csv']:
        digest = hashlib.sha256((folder/name).read_bytes()).hexdigest()
        if manifest['sha256'][name] != digest:
            raise ValueError(f'Empreinte différente : {name}')
    frame = read_requests(folder/'waf.csv')
    annotations = pd.read_csv(folder/'annotations.csv', dtype=str, keep_default_na=False)
    required = {'loki_timestamp_ns', 'split', 'session_id', 'scenario', 'is_attack'}
    if not required.issubset(annotations.columns):
        raise ValueError('Annotations incomplètes')
    for part in [frame, annotations]:
        if part.loki_timestamp_ns.eq('').any() or part.loki_timestamp_ns.duplicated().any():
            raise ValueError('Clé de jointure absente ou dupliquée')
    if set(frame.loki_timestamp_ns) != set(annotations.loki_timestamp_ns):
        raise ValueError('Requêtes et annotations différentes')
    if not annotations.is_attack.isin(['0', '1']).all():
        raise ValueError('Étiquette attendue : 0 ou 1')
    if set(annotations.split) != {'train', 'calibration', 'validation', 'test'}:
        raise ValueError('Quatre parties distinctes requises')
    frame = frame.merge(annotations[list(required)], on='loki_timestamp_ns', validate='one_to_one')
    frame['is_attack'] = frame.is_attack.astype(int)
    if frame.groupby('session_id').split.nunique().max() != 1:
        raise ValueError('Une session traverse plusieurs parties')
    parts = {name: frame[frame.split == name].copy() for name in ['train', 'calibration', 'validation', 'test']}
    previous_end = None
    for name, part in parts.items():
        stamps = pd.to_datetime(part.observed_at, utc=True)
        if previous_end is not None and stamps.min() <= previous_end:
            raise ValueError('Périodes non chronologiques ou chevauchantes')
        previous_end = stamps.max()
        if name in ['train', 'calibration'] and part.is_attack.any():
            raise ValueError('Train et calibration doivent être normaux')
    return parts, manifest


def evaluate(frame, scores, threshold):
    y = frame.is_attack.to_numpy(int)
    pred = (scores > threshold).astype(int)
    tn, fp, fn, tp = [int(v) for v in confusion_matrix(y, pred, labels=[0,1]).ravel()]
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/(tp+fn) if tp+fn else None
    episodes = []
    scored = frame.copy()
    scored['prediction'] = pred
    scored['score'] = scores
    for session, block in scored.groupby('session_id', sort=False):
        actual = block[block.is_attack == 1]
        if actual.empty:
            continue
        hits = actual[actual.prediction == 1]
        start = pd.to_datetime(actual.observed_at, utc=True).min()
        delay = (pd.to_datetime(hits.observed_at, utc=True).min()-start).total_seconds() if len(hits) else None
        episodes.append({'session_id':session, 'scenario':actual.scenario.iloc[0],
                         'attack_requests':len(actual), 'detected_requests':len(hits),
                         'detected':bool(len(hits)), 'delay_seconds_observed':delay})
    normal_sessions = scored.groupby('session_id').filter(lambda block: not block.is_attack.any())
    normal_alert_sessions = int(normal_sessions.groupby('session_id').prediction.max().sum()) if len(normal_sessions) else 0
    by_scenario = []
    for scenario, block in scored[scored.is_attack == 1].groupby('scenario'):
        by_scenario.append({'scenario':scenario, 'attack_requests':len(block),
                            'detected_requests':int(block.prediction.sum()), 'recall':float(block.prediction.mean())})
    return {'rows':len(frame), 'true_negative':tn, 'false_positive':fp, 'false_negative':fn,
            'true_positive':tp, 'precision':precision, 'recall':recall,
            'false_positive_rate':fp/(tn+fp) if tn+fp else None,
            'average_precision':float(average_precision_score(y,scores)) if len(set(y))==2 else None,
            'normal_sessions_with_alert':normal_alert_sessions,
            'episodes':episodes, 'by_scenario':by_scenario}


def train(dataset, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choisir un dossier vide ou nouveau')
    parts, manifest = load_dataset(dataset)
    if min(len(parts['train']),len(parts['calibration'])) < 100:
        raise ValueError('Train et calibration : au moins 100 requêtes chacun')
    model = IsolationForest(n_estimators=300, max_samples=512, contamination='auto',
                            random_state=42, n_jobs=1)
    t0=time.perf_counter()
    model.fit(extract_features(parts['train']))
    training_seconds=time.perf_counter()-t0
    threshold=float(np.quantile(-model.score_samples(extract_features(parts['calibration'])),.995))
    metadata={'model':'IsolationForest', 'feature_schema':SCHEMA, 'features':FEATURES,
              'threshold':threshold, 'quantile':.995, 'seed':42, 'n_estimators':300,
              'max_samples':512, 'data_origin':'synthetic', 'generator_seed':manifest['seed'],
              'source_sha256':manifest['sha256'], 'training_seconds':training_seconds,
              'evaluation_scope':'validation_only_test_not_scored',
              'versions':{'python':platform.python_version(), 'sklearn':sklearn.__version__,
                          'pandas':pd.__version__, 'numpy':np.__version__, 'joblib':joblib.__version__}}
    out.mkdir(parents=True,exist_ok=True)
    # Ce modèle est distinct des modèles historiques à cinq métriques.
    joblib.dump({'model':model,'metadata':metadata},out/'model.joblib')
    reports={}
    for name in ['train','calibration','validation']:
        frame=parts[name]
        scores=-model.score_samples(extract_features(frame))
        reports[name]=evaluate(frame,scores,threshold)
        result=frame[['observed_at','loki_timestamp_ns','client_ip','request_target','query',
                      'session_id','scenario','is_attack']].copy()
        result['anomaly_score']=scores
        result['predicted_anomaly']=(scores>threshold).astype(int)
        result.to_csv(out/f'{name}_predictions.csv',index=False)
    report={'metadata':metadata,'splits':reports}
    (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    v=reports['validation']
    print(json.dumps({'status':'trained','out':str(out),'validation':{k:v[k] for k in
          ['rows','true_positive','false_positive','false_negative','precision','recall']},
          'episodes_detected':sum(e['detected'] for e in v['episodes']),
          'episodes_total':len(v['episodes']), 'test_scored':False},indent=2))
    return report


def score(csv_path, model_path, out):
    out=Path(out)
    if out.exists():
        raise ValueError('Le fichier de sortie existe déjà')
    # joblib peut exécuter du code : ne charger que son propre artefact local.
    bundle=joblib.load(model_path)
    meta,model=bundle['metadata'],bundle['model']
    if meta.get('feature_schema')!=SCHEMA or meta.get('features')!=FEATURES:
        raise ValueError('Modèle incompatible : utiliser le modèle WAF de cet essai')
    if meta['versions']['sklearn']!=sklearn.__version__:
        raise ValueError('Version scikit-learn différente de l’entraînement')
    frame=read_requests(csv_path)
    scores=-model.score_samples(extract_features(frame))
    result=frame[['observed_at','loki_timestamp_ns','client_ip','request_target']].copy()
    result['anomaly_score']=scores
    result['threshold']=meta['threshold']
    result['predicted_anomaly']=(scores>meta['threshold']).astype(int)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8',newline='') as handle:
        result.to_csv(handle,index=False)
    print(json.dumps({'status':'scored','rows':len(result),'atypical_requests':int(result.predicted_anomaly.sum()),
                      'mode':'observation_only','out':str(out)}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    tr=sub.add_parser('train')
    tr.add_argument('--dataset',required=True)
    tr.add_argument('--out',required=True)
    sc=sub.add_parser('score')
    sc.add_argument('--csv',required=True)
    sc.add_argument('--model',required=True)
    sc.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='train':train(args.dataset,args.out)
    else:score(args.csv,args.model,args.out)


if __name__=='__main__': main()
