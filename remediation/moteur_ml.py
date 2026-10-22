#!/usr/bin/env python3
"""Moteur ML (SQL + brute force) : Loki/ML dans Docker, API Windows et actions Ansible dans WSL."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import ipaddress
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import time
from urllib.parse import urlsplit
import requests

# Configuration du PC hôte et des services : les secrets viennent de l’environnement
# ou de la saisie interactive, jamais du dépôt. Le modèle entraîné reste inchangé.
PROJECT_DIR=Path(os.environ.get('PHENIX_PROJECT_DIR',str(Path(__file__).resolve().parents[1])))
API=os.environ.get('PHENIX_API','http://localhost:8080').rstrip('/')
SERVICE_USER=os.environ.get('SERVICE_USER','service_remediation')
SERVICE_PASSWORD=os.environ.get('DEMO_USER_PASSWORD','')
NETWORK=os.environ.get('LOKI_DOCKER_NETWORK','phenix_ops')
IMAGE=os.environ.get('DETECTOR_IMAGE','phenix-detector')
SQL_MODEL=PROJECT_DIR/'backend/ML/experiments/local-sql-v1/model.joblib'
BRUTE_MODEL=PROJECT_DIR/'backend/ML/experiments/local-bruteforce-v1/model.joblib'
STATE_FILE=PROJECT_DIR/'remediation/state-ml.json'
INTERVALLE_S=5
NS=10**9


def check_url():
    """URL vue depuis Ansible : configuration explicite, sinon passerelle WSL."""
    configured=os.environ.get('CHECK_URL')
    if configured:return configured
    if platform.system()!='Windows':return API+'/health'
    r=subprocess.run(['wsl','ip','-4','route','show','default'],capture_output=True,text=True,check=True,timeout=10)
    for line in r.stdout.splitlines():
        fields=line.split()
        if fields and fields[0]=='default' and 'via' in fields:
            host=str(ipaddress.ip_address(fields[fields.index('via')+1]))
            return f'http://{host}:8080/health'
    raise ValueError('Passerelle WSL introuvable : définir CHECK_URL')


def action_ansible(action,**params):
    # Arguments séparés, jamais shell=True ; la liste blanche finale reste dans run.sh.
    if action not in {'block_ip','verify'}:raise ValueError('Action refusée par le moteur ML commun')
    cmd=['bash','infra/ansible/run.sh',action,*[f'{k}={v}' for k,v in params.items()]]
    if platform.system()=='Windows':cmd=['wsl','--cd',str(PROJECT_DIR),*cmd];cwd=None
    else:cwd=str(PROJECT_DIR)
    r=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,timeout=300,encoding='utf-8',errors='replace')
    return r.returncode==0,(r.stdout+r.stderr)[-2000:]


# Authentifier le compte de service pour les routes incidents. Un échec HTTP
# interrompt la tentative ; aucun jeton ni mot de passe n’est affiché.
def get_token():
    r=requests.post(API+'/api/auth/login',json={'username':SERVICE_USER,'password':SERVICE_PASSWORD},timeout=5)
    r.raise_for_status();return r.json()['access_token']


# Enregistrer uniquement les champs acceptés par l’API. L’IP et le score
# sont déjà résumés dans la description produite par le détecteur.
def ouvrir_incident(token,alerte):
    body={key:alerte[key] for key in ['event_type','severity','source','target_service','description']}
    r=requests.post(API+'/api/incidents',json=body,headers={'Authorization':'Bearer '+token},timeout=5)
    r.raise_for_status();return r.json()['id']


# Clôturer après le succès des actions. Cette vérification de disponibilité
# ne démontre pas, à elle seule, une transaction réussie ou le blocage effectif.
def resoudre_incident(token,incident_id,action_taken):
    r=requests.patch(f'{API}/api/incidents/{incident_id}/resolve',json={'action_taken':action_taken},
                     headers={'Authorization':'Bearer '+token},timeout=5)
    r.raise_for_status()


def detecter_alertes(start_ns,end_ns):
    """Monter deux modèles figés et demander une unique collecte partagée."""
    for model in (SQL_MODEL, BRUTE_MODEL):
        if not model.is_file():
            raise FileNotFoundError(f'Modèle absent : {model}')
    cmd=['docker','run','--rm','--network',NETWORK,
         '--mount',f'type=bind,source={SQL_MODEL.resolve()},target=/model/sql.joblib,readonly',
         '--mount',f'type=bind,source={BRUTE_MODEL.resolve()},target=/model/bruteforce.joblib,readonly',
         IMAGE,'python','-m','detector.live_combined',
         '--sql-model','/model/sql.joblib','--brute-model','/model/bruteforce.joblib',
         '--start-ns',str(start_ns),'--end-ns',str(end_ns),
         '--url',os.environ.get('LOKI_URL','http://loki:3100'),
         '--query',os.environ.get('LOKI_QUERY','{container="phenix-waf-1"} |= " HTTP/"')]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=180,encoding='utf-8',errors='replace')
    if r.returncode:
        raise RuntimeError('Collecte/scoring Docker échoué : '+r.stderr[-1500:])
    payload=json.loads(r.stdout)
    if not isinstance(payload.get('alerts'),list):
        raise ValueError('Réponse détecteur invalide')
    # Le routage de l’action ne dépend jamais d’une valeur arbitraire issue des logs.
    for alert in payload['alerts']:
        if alert.get('detection_kind') not in {'sql_injection','bruteforce'}:
            raise ValueError('Famille de détection inconnue')
    return payload


# Initialiser le curseur et les mémoires de dédoublonnage. L’état commun est
# indépendant des anciens moteurs séparés et persiste uniquement en mode actif.
def fresh_state(now_ns):
    return {'version':1,'cursor_ns':now_ns-30*NS,'seen':{},'pending':{},'cooldown':{}}


# Remplacer le fichier d’état via un fichier temporaire pour limiter
# les écritures partielles si le programme est interrompu.
def save_state(state,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


# Refuser le blocage des adresses locales et hôtes identifiés. Cette protection
# complète celle d’Ansible ; elle dépend aussi de la fiabilité de l’IP journalisée.
def protected_reason(alert,url):
    ip=ipaddress.ip_address(alert['ip'])
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:return 'adresse locale ou spéciale'
    protected={alert.get('peer_ip',''),urlsplit(url).hostname or '',urlsplit(API).hostname or ''}
    protected.update(value.strip() for value in os.environ.get('PROTECTED_IPS','').split(',') if value.strip())
    try:protected.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(),None))
    except socket.gaierror:pass
    if str(ip) in protected:return 'adresse hôte/passerelle protégée'
    return None


def enqueue(state,alerts,now_ns):
    """Identité stable par log et un seul incident en attente par IP."""
    for alert in alerts:
        event=alert['detection_id'];ip=str(ipaddress.ip_address(alert['ip']));alert['ip']=ip
        if event in state['seen']:continue
        state['seen'][event]=int(alert['loki_timestamp_ns'])
        if state['cooldown'].get(ip,0)>now_ns:continue
        if any(item['alert']['ip']==ip for item in state['pending'].values()):continue
        state['pending'][event]={'alert':alert,'incident_id':None,'attempts':0,'last_attempt_ns':0}


def traiter(token,entry,url,save):
    """Reprend le même incident enregistré après un échec d'action ou de vérification."""
    alert=entry['alert']
    if entry['incident_id'] is None:
        entry['incident_id']=ouvrir_incident(token,alert)
        save()
        print(f"  incident #{entry['incident_id']} ouvert",flush=True)
    reason=protected_reason(alert,url)
    if reason:
        print(f"  {alert['ip']} : {reason}, aucun blocage ; incident laissé ouvert",flush=True)
        return 'protected'
    # Bloquer d’abord l’IP, puis vérifier la disponibilité via le WAF.
    # Au moindre échec, garder l’incident ouvert et demander une nouvelle tentative.
    ok,output=action_ansible('block_ip',ip=alert['ip'],reason=alert['detection_kind'])
    print(f"  block_ip : {'OK' if ok else 'ÉCHEC'}",flush=True)
    if not ok:
        print(output,flush=True);return 'retry'
    ok,output=action_ansible('verify',service='backend',check_url=url)
    print(f"  verify   : {'OK' if ok else 'ÉCHEC'}",flush=True)
    if not ok:
        print(output,flush=True);return 'retry'
    resoudre_incident(token,entry['incident_id'],f"block_ip {alert['ip']} ({alert['detection_kind']} ML) + verify OK")
    print(f"  incident #{entry['incident_id']} résolu",flush=True)
    return 'resolved'


# Reprendre les incidents en attente au maximum trois fois, à 30 secondes
# d’intervalle. Sauvegarder leur identifiant évite de les recréer après chaque échec.
def process_pending(state,url,path,now_ns):
    ready=[key for key,entry in state['pending'].items() if now_ns-entry['last_attempt_ns']>=30*NS]
    if not ready:return
    token=get_token()
    for key in ready:
        entry=state['pending'][key];entry['attempts']+=1;entry['last_attempt_ns']=now_ns
        save_state(state,path)
        print('[ALERTE] '+entry['alert']['description'],flush=True)
        try:
            result=traiter(token,entry,url,lambda:save_state(state,path))
        except requests.HTTPError as exc:
            # Une clôture peut avoir réussi côté serveur malgré une réponse perdue.
            # Ne pas interpréter aveuglément un 409 comme une résolution confirmée.
            print(f"[ERREUR API] {exc}",flush=True);result='retry'
        except (requests.RequestException,subprocess.SubprocessError,OSError) as exc:
            print(f'[ERREUR] {type(exc).__name__}: {exc}',flush=True);result='retry'
        if result!='retry' or entry['attempts']>=3:
            # Garde un historique local de la dernière action par IP et évite une rafale d'incidents.
            state.setdefault('last_incident',{})[entry['alert']['ip']]={
                'incident_id':entry['incident_id'],'result':result if result!='retry' else 'failed',
                'attempts':entry['attempts'],'at':datetime.now(timezone.utc).isoformat()}
            state['cooldown'][entry['alert']['ip']]=now_ns+300*NS
            del state['pending'][key]
            if result=='retry':print('  Trois essais en échec : incident laissé ouvert, diagnostic requis.',flush=True)
        save_state(state,path)


# Lire une fenêtre de logs, scorer puis dédoublonner. Sans --apply, afficher
# les détections uniquement : aucune API incidente ni action Ansible n’est appelée.
def cycle(state,apply=False,url=None,path=STATE_FILE):
    now=time.time_ns();end=min(now-2*NS,state['cursor_ns']+60*NS)
    if end>state['cursor_ns']:
        # Relecture de 120 s pour les retards courants d'ingestion, dédoublonnée par événement.
        start=max(0,state['cursor_ns']-120*NS)
        payload=detecter_alertes(start,end)
        new=[a for a in payload['alerts'] if a['detection_id'] not in state['seen']]
        print(f"[ML] {payload['scanned']} logs lus, SQL={sum(a['detection_kind']=='sql_injection' for a in new)}, brute force={sum(a['detection_kind']=='bruteforce' for a in new)} nouvelles détections",flush=True)
        if apply:enqueue(state,new,now)
        else:
            for alert in new:
                state['seen'][alert['detection_id']]=int(alert['loki_timestamp_ns'])
                print(f"[OBSERVATION] type={alert['detection_kind']} IP={alert['ip']} score={alert['score']:.4f} seuil={alert['threshold']:.4f}",flush=True)
        state['cursor_ns']=end
        state['seen']={key:stamp for key,stamp in state['seen'].items() if stamp>=end-600*NS}
        state['cooldown']={ip:stamp for ip,stamp in state['cooldown'].items() if stamp>now}
        if apply:save_state(state,path)
    if apply:process_pending(state,url,path,now)


# Choisir explicitement observation ou remédiation, restaurer l’état actif,
# puis répéter les cycles jusqu’à --once ou Ctrl+C.
def main():
    global SERVICE_PASSWORD
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Exécuter API et actions Ansible ; sinon observation seule')
    parser.add_argument('--once',action='store_true',help='Un seul cycle, puis retour au terminal')
    args=parser.parse_args()
    url=check_url() if args.apply else None
    if args.apply and not SERVICE_PASSWORD:SERVICE_PASSWORD=getpass('Mot de passe de démo : ')
    # Seul le mode actif recharge son historique. Une observation repart sur
    # les logs récents sans modifier l’état des remédiations.
    if args.apply and STATE_FILE.exists():
        state=json.loads(STATE_FILE.read_text(encoding='utf-8'))
        if state.get('version')!=1:raise ValueError('État incompatible')
    else:state=fresh_state(time.time_ns())

    # Après un long arrêt, reprendre les logs récents sans effacer
    # les incidents en attente ni la mémoire des détections.
    now_ns = time.time_ns()
    if now_ns - state['cursor_ns'] > 180 * NS:
        print(
            "[REPRISE] Curseur ancien : retour aux logs récents. "
            "L'historique intermédiaire ne sera pas analysé.",
            flush=True,
        )
        state['cursor_ns'] = now_ns - 30 * NS
        if args.apply:
            save_state(state, STATE_FILE)

    print('Moteur ML (SQL + brute force) : '+('REMÉDIATION ACTIVE' if args.apply else 'OBSERVATION'),flush=True)

    if url:print('Vérification depuis Ansible : '+url,flush=True)
    try:
        while True:
            try:cycle(state,args.apply,url)
            # Une erreur de cycle est visible et n’arrête pas la surveillance ;
            # en mode --once, elle est propagée pour rendre le test vérifiable.
            except Exception as exc:
                print(f'[ERREUR] {type(exc).__name__}: {exc}',flush=True)
                if args.once:raise
            if args.once:break
            time.sleep(INTERVALLE_S)
    except KeyboardInterrupt:print('\nMoteur arrêté.',flush=True)


if __name__=='__main__':main()
