"""Paiement de démonstration aller-retour, contrôlé et repris par idempotence."""
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import uuid


class ProbeError(Exception):
    """Erreur présentable sans exposer mot de passe, jeton ou corps de réponse."""


class PaymentProbe:
    def __init__(self, api, users, passwords, state_path, transport=None):
        # Le journal ne contient que références et soldes ; les secrets restent en mémoire.
        self.api = api.rstrip('/')
        self.users, self.passwords = users, passwords
        self.path = Path(state_path)
        self.transport = transport or self._http
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _http(self, method, route, payload=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(self.api + route, method=method, headers=headers,
                    data=None if payload is None else json.dumps(payload).encode())
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            # Ne pas recopier le corps brut d’une réponse de sécurité dans les logs.
            return exc.code, {}

    def save(self, state):
        # Écriture atomique ; le volume /state doit persister après recréation du conteneur.
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, self.path)

    def account(self, token):
        code, body = self.transport('GET', '/api/accounts/me', token=token)
        if code != 200:
            raise ProbeError(f'Lecture du compte refusée (HTTP {code})')
        if body.get('status') != 'ACTIVE':
            raise ProbeError('Compte de test non actif')
        # Decimal évite les comparaisons de soldes en virgule flottante.
        balance = Decimal(str(body['balance']))
        if not balance.is_finite():
            raise ProbeError('Solde invalide')
        return {'id': int(body['id']), 'balance': str(balance)}

    def pay(self, token, sender, receiver, amount, key):
        # Un timeout n’établit pas si le commit a eu lieu : rejouer la même clé.
        # La clé est sauvegardée AVANT le premier appel et réutilisée au redémarrage.
        for attempt in range(3):
            try:
                code, body = self.transport('POST', '/api/transactions',
                    {'idempotency_key': key, 'receiver_account_id': receiver, 'amount': amount}, token)
                if code in (200, 201):
                    valid = (body.get('status') == 'SUCCESS' and body.get('idempotency_key') == key
                        and body.get('sender_account_id') == sender
                        and body.get('receiver_account_id') == receiver
                        and Decimal(str(body.get('amount'))) == Decimal(amount))
                    if not valid or not body.get('id'):
                        raise ProbeError('Réponse de transaction incohérente ; contrôle manuel requis')
                    return str(body['id']), code
                if code < 500:
                    raise ProbeError(f'Paiement refusé (HTTP {code})')
            except (urllib.error.URLError, OSError, TimeoutError):
                pass
            if attempt < 2:
                time.sleep(.2)
        raise ProbeError('Résultat du paiement indéterminé ; même clé conservée pour reprise')

    def check_record(self, token, tx_id, sender, receiver, amount, key):
        # Une restauration de base peut supprimer un paiement déjà confirmé.
        # Vérifier sa présence avant toute compensation évite de rembourser un
        # aller qui n’existe plus dans l’état courant de la base.
        code, body = self.transport('GET', '/api/transactions/' + tx_id, token=token)
        if (code != 200 or str(body.get('id')) != tx_id or body.get('status') != 'SUCCESS'
            or body.get('idempotency_key') != key or body.get('sender_account_id') != sender
            or body.get('receiver_account_id') != receiver
            or Decimal(str(body.get('amount'))) != Decimal(amount)):
            raise ProbeError('Paiement confirmé absent ou incohérent ; vérifier une éventuelle restauration de base')

    def run(self, require_fresh=False):
        # Le serveur /run et le test périodique sont sérialisés dans le même processus.
        if not self.lock.acquire(timeout=30):
            return {'ok': False, 'at': self.now(), 'http_status': None, 'detail': 'Test déjà occupé'}
        state = None
        try:
            stored = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
            state = stored if stored and stored.get('phase') != 'done' else None
            resumed = state is not None
            # Renouveler les JWT sans les écrire dans le journal persistant.
            if not all(self.passwords):
                raise ProbeError('Mot de passe de test absent')
            tokens = []
            for user, password in zip(self.users, self.passwords):
                code, body = self.transport('POST', '/api/auth/login', {'username': user, 'password': password})
                if code != 200 or not body.get('access_token'):
                    raise ProbeError(f'Authentification du compte de test refusée (HTTP {code})')
                tokens.append(body['access_token'])
            accounts = [self.account(t) for t in tokens]
            if state is None:
                if accounts[0]['id'] == accounts[1]['id']:
                    raise ProbeError('Les deux comptes de test doivent être distincts')
                if Decimal(accounts[0]['balance']) < Decimal('1.00'):
                    raise ProbeError('Solde du compte de test insuffisant')
                run_id = uuid.uuid4().hex
                state = {'version': 1, 'run_id': run_id, 'started_at': self.now(), 'users': list(self.users),
                    'accounts': accounts, 'amount': '1.00', 'phase': 'forward', 'error': None,
                    'mid_verified': False, 'forward_key': f'probe-{run_id}-out', 'refund_key': f'probe-{run_id}-back'}
                self.save(state)
            else:
                # Empêcher une reprise sur d’autres comptes ou une base réinitialisée.
                if (state.get('version') != 1 or state['users'] != list(self.users)
                    or [a['id'] for a in accounts] != [a['id'] for a in state['accounts']]):
                    raise ProbeError('État de paiement incompatible avec les comptes ; contrôle manuel requis')
            a, b = state['accounts']
            amount = Decimal(state['amount'])
            if state['phase'] == 'forward':
                tx, code = self.pay(tokens[0], a['id'], b['id'], state['amount'], state['forward_key'])
                state.update(forward_id=tx, http_status=code, phase='refund')
                self.save(state)
                # Même si le contrôle intermédiaire échoue, tenter le retour : ne
                # pas laisser volontairement l’euro transféré pour un simple échec de lecture.
                try:
                    mid = [self.account(t) for t in tokens]
                    if ([Decimal(x['balance']) for x in mid] !=
                        [Decimal(a['balance']) - amount, Decimal(b['balance']) + amount]):
                        state['error'] = 'Variation de solde intermédiaire inattendue (activité concurrente possible)'
                    else:
                        state['mid_verified'] = True
                except (ProbeError, urllib.error.URLError, OSError, ValueError, DecimalException, KeyError):
                    state['error'] = 'Contrôle intermédiaire impossible'
                self.save(state)
            if state['phase'] == 'refund':
                self.check_record(tokens[0], state['forward_id'], a['id'], b['id'], state['amount'], state['forward_key'])
                tx, code = self.pay(tokens[1], b['id'], a['id'], state['amount'], state['refund_key'])
                state.update(refund_id=tx, http_status=code, phase='final')
                self.save(state)
            if state['phase'] != 'final':
                raise ProbeError('Phase de paiement inconnue')
            self.check_record(tokens[0], state['forward_id'], a['id'], b['id'], state['amount'], state['forward_key'])
            self.check_record(tokens[1], state['refund_id'], b['id'], a['id'], state['amount'], state['refund_key'])
            final = [self.account(t) for t in tokens]
            balances_ok = [Decimal(x['balance']) for x in final] == [Decimal(a['balance']), Decimal(b['balance'])]
            if not balances_ok:
                state['error'] = 'Soldes finaux différents des soldes initiaux (activité concurrente possible)'
            # Une reprise d’un test antérieur rend les fonds, mais ne prouve pas
            # qu’un paiement NOUVEAU a été effectué après l’action Ansible courante.
            if not state.get('mid_verified') and not state['error']:
                state['error'] = 'Contrôle intermédiaire non confirmé'
            ok = not state['error'] and not (require_fresh and resumed)
            detail = state['error'] or ('Ancien test repris ; relancer pour une nouvelle preuve' if require_fresh and resumed
                                       else 'Paiement 1 EUR + retour réussis ; soldes initiaux retrouvés')
            result = {'ok': ok, 'http_status': state.get('http_status'), 'at': self.now(),
                      'started_at': state['started_at'], 'detail': detail, 'run_id': state['run_id'],
                      'forward_id': state.get('forward_id'), 'refund_id': state.get('refund_id'),
                      'compensated': True, 'balances_restored': balances_ok}
            state.update(phase='done', result=result)
            self.save(state)
            return result
        except (ProbeError, urllib.error.URLError, OSError, ValueError, DecimalException, KeyError, TypeError) as exc:
            # Conserver une opération incomplète pour reprise. Ne pas annoncer
            # l’absence de débit si le résultat réseau est indéterminé.
            return {'ok': False, 'http_status': None, 'at': self.now(),
                    'detail': str(exc) if isinstance(exc, ProbeError) else f'Test impossible ({type(exc).__name__})',
                    'run_id': state.get('run_id') if state else None,
                    'pending': bool(state and state.get('phase') != 'done')}
        finally:
            self.lock.release()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
