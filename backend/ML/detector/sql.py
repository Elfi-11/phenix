"""Reconnaissance supervisée normal/SQL, hors action système et hors test final."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import time
from urllib.parse import quote, quote_plus, unquote_plus

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from detector.collect import FIELDS, parse_access, time_ns
from detector.generate_waf import format_time
from detector.waf import read_requests, evaluate

SCHEMA = 'waf-sql-char-supervised-v1'
# Ces motifs définissent les exemples synthétiques et leurs étiquettes.
# Ils ne sont jamais consultés par le classifieur à l'inférence.
TEMPLATES = {
 'boolean': [
  "{prefix}' OR {n}={n} --", "{prefix}' AND '{word}'='{word}' --",
  "{prefix}' OR ({n}={n}) --", "{prefix}' OR {n} < {m} --", "{prefix}' AND ({n} <= {m}) --"],
 'union': [
  "{prefix}' UNION SELECT NULL --", "{prefix}' UNION ALL SELECT NULL,NULL --",
  "{prefix}' UNION SELECT {n},NULL --", "{prefix}' UNION ALL SELECT NULL,{n},NULL --",
  "{prefix}' UNION SELECT NULL,NULL,{n},NULL --"],
 'comment': [
  "{prefix}' -- {word}", "{prefix}' /* {word} */", "{prefix}'--{word}",
  "{prefix}' /*{word}*/ --", "{prefix}' -- ({word})"],
 'time': [
  "{prefix}' AND sleep(0) --", "{prefix}' AND benchmark(0,1) --",
  "{prefix}' AND pg_sleep(0) IS NULL --", "{prefix}' OR sleep(0)=0 --",
  "{prefix}' AND (benchmark(0,1)=0) --"],
 'metadata': [
  "{prefix}' UNION SELECT column_name FROM information_schema.columns --",
  "{prefix}' UNION SELECT table_name FROM information_schema.tables --",
  "{prefix}' UNION ALL SELECT table_name FROM information_schema.tables --",
  "{prefix}' UNION SELECT NULL,column_name FROM information_schema.columns --",
  "{prefix}' UNION ALL SELECT NULL,table_name FROM information_schema.tables --"],
}
PROTOCOL = [('train',160),('calibration',40),('validation',40),('test',40)]
WORDS = {'train':['azur','bois','cuivre','delta','eclair','fleur'],
         'calibration':['galet','herbe','iris'], 'validation':['jade','kiwi','lilas'],
         'test':['miel','nuage','olive']}
NORMAL = ["commande {word} {n}", "O'Reilly {word}", "Union des clients {word}",
          "guide UNION SELECT pour {word}", "exemple OR {n}={n} expliqué",
          "commentaire -- {word}", "fonction sleep(0) documentation {word}",
          "information_schema définition {word}", "référence ({word}) + {n}",
          "promotion {n}% pour {word}", "statut={prefix} & client={word}",
          "'citation {word}'", "{word}/{n}"]


def normalize_query(value):
    if not isinstance(value,str) or len(value)>16384:
        raise ValueError('Query absente ou hors contrat (>16384 caractères)')
    # Normalisation commune train/scoring, sans règle de classe ni mot-clé SQL.
    return re.sub(r'\s+', ' ', unquote_plus(unquote_plus(value))).strip().lower()


def texts(frame):
    if 'query' not in frame:
        raise ValueError('Colonne query absente')
    return frame['query'].map(normalize_query).tolist()


def generate(out, seed=20261022):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Dossier de sortie non vide')
    out.mkdir(parents=True,exist_ok=True)
    stats={};position=0
    labels={'container':'phenix-waf-1','service':'waf','service_name':'waf'}
    with (out/'waf.log').open('w',encoding='utf-8') as raw, \
         (out/'waf.csv').open('w',encoding='utf-8',newline='') as parsed, \
         (out/'annotations.csv').open('w',encoding='utf-8',newline='') as annotated:
        writer=csv.DictWriter(parsed,fieldnames=FIELDS);writer.writeheader()
        truth=csv.DictWriter(annotated,fieldnames=['loki_timestamp_ns','split','session_id','scenario','template_id','is_attack']);truth.writeheader()
        for split_index,(split,count) in enumerate(PROTOCOL):
            rng=random.Random(seed+split_index*100003)
            stats[split]={'sessions':count,'requests':0,'attack_requests':0}
            families=list(TEMPLATES)
            for session in range(count):
                start=datetime(2026,11,10,tzinfo=timezone.utc)+timedelta(minutes=position*10)
                position+=1
                client=f'192.0.2.{rng.randint(1,254)}'
                agent=rng.choice(['Mozilla/5.0 Workshop/1.0','curl/8.0','python-requests/2.32'])
                family=families[(session//2)%len(families)] if session%2==0 else 'normal'
                pace=rng.choice([1,2,5,8])
                for j in range(50):
                    malicious=family!='normal' and 16<=j<33
                    params={'prefix':rng.choice(['SUCCESS','FAILED','PENDING']),
                            'word':rng.choice(WORDS[split]),'n':rng.randint(1,999)}
                    params['m']=params['n']+rng.randint(1,50)
                    if malicious:
                        k=rng.choice([0,1]) if split=='train' else {'calibration':2,'validation':3,'test':4}[split]
                        payload=TEMPLATES[family][k].format(**params)
                        template_id=f'{family}-{k}'
                        route='/api/attackme/search';method='GET'
                    else:
                        route=rng.choices(['/api/attackme/search','/docs','/openapi.json','/api/accounts/me','/api/auth/login'],weights=[70,7,3,15,5])[0]
                        method='POST' if route=='/api/auth/login' else 'GET'
                        if rng.random()<.2:
                            payload=params['prefix'];template_id='normal-common-status'
                        else:
                            k=rng.randrange(len(NORMAL));payload=NORMAL[k].format(**params)
                            template_id=f'normal-{k}'
                    if route=='/api/attackme/search':
                        if rng.random()<.2:payload=payload.swapcase()
                        encoding=rng.choice(['space','plus','double'])
                        encoded=quote_plus(payload,safe='') if encoding=='plus' else quote(payload,safe='')
                        if encoding=='double':encoded=quote(encoded,safe='')
                        target=route+'?q='+encoded
                    else:target=route
                    status=rng.choices([200,401,403,404,500],weights=[88,4,3,3,2])[0]
                    size=rng.choice([2,24,80,206,548,934,13657])
                    stamp=start+timedelta(seconds=j*pace)
                    line=f'172.26.0.1 - - [{format_time(stamp)}] "{method} {target} HTTP/1.1" {status} {size} "-" "{agent}" "{client}"'
                    ns=str(time_ns(stamp.isoformat())+j+1)
                    raw.write(line+'\n');writer.writerow(parse_access(line,labels,ns))
                    truth.writerow({'loki_timestamp_ns':ns,'split':split,'session_id':f'{split}-{session:04d}',
                                    'scenario':family if malicious else 'normal','template_id':template_id,'is_attack':int(malicious)})
                    stats[split]['requests']+=1;stats[split]['attack_requests']+=int(malicious)
    manifest={'origin':'synthetic','schema_version':'waf-sql-supervised-v1','seed':seed,'splits':stats,
              'target':'tentative SQL connue, sans preuve de succès',
              'split_policy':'sessions séparées et gabarits SQL distincts ; mêmes familles connues',
              'limits':['Gabarits proches, familles et générateur connus : évaluation exploratoire',
                        'Les requêtes normales partagent des gabarits, avec vocabulaire variant selon les périodes',
                        'Ni SQL exécuté ni trafic envoyé ; statuts et tailles simplifiés et indépendants des classes',
                        'Aucun corps POST disponible dans ce format de logs'],
              'sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['waf.log','waf.csv','annotations.csv']}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest


def load_dataset(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('origin')!='synthetic' or manifest.get('schema_version')!='waf-sql-supervised-v1':
        raise ValueError('Utiliser le nouveau jeu supervisé, pas le jeu WAF normal seul')
    for name in ['waf.csv','annotations.csv']:
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=manifest['sha256'][name]:raise ValueError('Empreinte source différente')
    frame=read_requests(folder/'waf.csv')
    ann=pd.read_csv(folder/'annotations.csv',dtype=str,keep_default_na=False)
    expected=['loki_timestamp_ns','split','session_id','scenario','template_id','is_attack']
    if not set(expected).issubset(ann):raise ValueError('Annotations incomplètes')
    for item in [frame,ann]:
        if item.loki_timestamp_ns.eq('').any() or item.loki_timestamp_ns.duplicated().any():raise ValueError('Clé absente ou dupliquée')
    if set(frame.loki_timestamp_ns)!=set(ann.loki_timestamp_ns):raise ValueError('Jointure incomplète')
    if not ann.is_attack.isin(['0','1']).all():raise ValueError('Étiquettes invalides')
    if set(ann.split)!={'train','calibration','validation','test'}:raise ValueError('Quatre parties requises')
    frame=frame.merge(ann[expected],on='loki_timestamp_ns',validate='one_to_one')
    frame['is_attack']=frame.is_attack.astype(int)
    if frame.groupby('session_id').split.nunique().max()!=1:raise ValueError('Session partagée')
    attacks=frame[frame.is_attack==1]
    if attacks.groupby('template_id').split.nunique().max()!=1:raise ValueError('Gabarit SQL partagé entre périodes')
    # Les encodages d'une même query SQL ne doivent pas traverser les parties.
    normalised=attacks.assign(normalised=texts(attacks))
    if normalised.groupby('normalised').split.nunique().max()!=1:raise ValueError('Query SQL identique entre périodes')
    parts={name:frame[frame.split==name].copy() for name in ['train','calibration','validation','test']}
    end=None
    for name,part in parts.items():
        if set(part.is_attack)!={0,1}:raise ValueError('Deux classes requises dans chaque période')
        stamps=pd.to_datetime(part.observed_at,utc=True)
        if end is not None and stamps.min()<=end:raise ValueError('Périodes chevauchantes')
        end=stamps.max()
    return parts,manifest


def new_model():
    return make_pipeline(TfidfVectorizer(analyzer='char',ngram_range=(2,5),min_df=1,
                                        max_features=40000,sublinear_tf=True),
                         LogisticRegression(C=1.0,class_weight='balanced',max_iter=1000,random_state=42))


def choose_threshold(y,scores,max_fpr=.01):
    """Sur calibration uniquement : rappel maximal sous contrainte empirique de FP."""
    y=np.asarray(y,dtype=int);scores=np.asarray(scores,dtype=float)
    if set(y)!={0,1} or not np.isfinite(scores).all():raise ValueError('Calibration invalide')
    if not 0<=max_fpr<1:raise ValueError('Budget de faux positifs invalide')
    # Comparateur strict > : inclut le cas aucune alerte. Pas de seuil optimisé sur validation.
    candidates=np.r_[np.nextafter(scores.min(),-np.inf),np.unique(scores)]
    best=None
    for threshold in candidates:
        p=scores>threshold
        fpr=float(p[y==0].mean());recall=float(p[y==1].mean())
        if fpr<=max_fpr:
            rank=(recall,-fpr,float(threshold))
            if best is None or rank>best[0]:best=(rank,float(threshold))
    return best[1]


def train(dataset,out):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Dossier non vide')
    parts,manifest=load_dataset(dataset)
    model=new_model();t0=time.perf_counter()
    model.fit(texts(parts['train']),parts['train'].is_attack)
    duration=time.perf_counter()-t0
    cal=model.predict_proba(texts(parts['calibration']))[:,1]
    threshold=choose_threshold(parts['calibration'].is_attack,cal)
    meta={'model':'TFIDF_char_LogisticRegression','feature_schema':SCHEMA,'threshold':threshold,
          'threshold_policy':'rappel maximal sous taux FP calibration <= 1%, départage par FP puis seuil supérieur',
          'score_kind':'classifier_probability_uncalibrated','seed':42,'ngram_range':[2,5],
          'C':1.0,'class_weight':'balanced','data_origin':'synthetic','generator_seed':manifest['seed'],
          'source_sha256':manifest['sha256'],'training_seconds':duration,
          'vocabulary_size':len(model.named_steps['tfidfvectorizer'].vocabulary_),
          'scope':'validation_only_test_not_scored','versions':{'sklearn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__}}
    out.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':model,'metadata':meta},out/'model.joblib')
    # Quelques poids appris pour inspection, pas une liste de règles exécutées.
    weights=pd.DataFrame({'ngram':model.named_steps['tfidfvectorizer'].get_feature_names_out(),
                          'weight_sql':model.named_steps['logisticregression'].coef_[0]})
    pd.concat([weights.nlargest(30,'weight_sql'),weights.nsmallest(30,'weight_sql')]).to_csv(out/'learned_ngrams.csv',index=False)
    reports={}
    for name in ['train','calibration','validation']:
        part=parts[name];scores=model.predict_proba(texts(part))[:,1]
        reports[name]=evaluate(part,scores,threshold)
        result=part[['observed_at','loki_timestamp_ns','client_ip','request_target','query','session_id','scenario','template_id','is_attack']].copy()
        result['sql_score']=scores;result['predicted_sql']=(scores>threshold).astype(int)
        result.to_csv(out/f'{name}_predictions.csv',index=False)
    report={'metadata':meta,'splits':reports}
    (out/'metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    v=reports['validation']
    print(json.dumps({'status':'trained','out':str(out),'threshold':threshold,
                      'validation':{k:v[k] for k in ['rows','true_positive','false_positive','false_negative','precision','recall']},
                      'by_scenario':v['by_scenario'],'test_scored':False},indent=2))
    return report


def score(csv_path,model_path,out):
    out=Path(out)
    if out.exists() or out.with_suffix('.detections.jsonl').exists():raise ValueError('Sortie existante')
    # Un artefact joblib est exécutable : charger uniquement son propre modèle local.
    bundle=joblib.load(model_path);meta=bundle['metadata'];model=bundle['model']
    if meta.get('feature_schema')!=SCHEMA or meta['versions']['sklearn']!=sklearn.__version__:raise ValueError('Modèle incompatible')
    frame=read_requests(csv_path)
    scores=model.predict_proba(texts(frame))[:,1]
    result=frame[['observed_at','loki_timestamp_ns','client_ip','request_target']].copy()
    result['sql_score']=scores;result['threshold']=meta['threshold'];result['predicted_sql']=(scores>meta['threshold']).astype(int)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8',newline='') as handle:result.to_csv(handle,index=False)
    # Fichier local de raccordement, pas le contrat d'alerte officiel de l'équipe.
    with out.with_suffix('.detections.jsonl').open('x',encoding='utf-8') as handle:
        for row in result[result.predicted_sql==1].itertuples(index=False):
            event={'observed_at':row.observed_at,'client_ip':row.client_ip,
                   'loki_timestamp_ns':row.loki_timestamp_ns,'detection_type':'suspected_sql_injection',
                   'source':'ML','sql_score':row.sql_score,'threshold':meta['threshold'],
                   'mode':'observation','model_schema':SCHEMA}
            handle.write(json.dumps(event,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'scored','rows':len(result),'sql_detections':int(result.predicted_sql.sum()),'mode':'observation_only'}))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    gen=sub.add_parser('generate');gen.add_argument('--out',required=True);gen.add_argument('--seed',type=int,default=20261022)
    tr=sub.add_parser('train');tr.add_argument('--dataset',required=True);tr.add_argument('--out',required=True)
    sc=sub.add_parser('score');sc.add_argument('--csv',required=True);sc.add_argument('--model',required=True);sc.add_argument('--out',required=True)
    a=p.parse_args()
    if a.command=='generate':print(json.dumps(generate(a.out,a.seed)['splits'],indent=2))
    elif a.command=='train':train(a.dataset,a.out)
    else:score(a.csv,a.model,a.out)


if __name__=='__main__':main()
