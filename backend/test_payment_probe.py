"""Recette hors réseau : ledger fictif, commits, pertes de réponse et reprise."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from payment_probe import PaymentProbe


class Ledger:
    def __init__(self):
        self.balances = {1: Decimal('100.00'), 2: Decimal('20.00')}
        self.payments = {}
        self.calls = []
        self.refund_down = False
        self.lose_forward = False
        self.mid_down = False
        self.final_drift = False

    def __call__(self, method, route, payload=None, token=None):
        if route == '/api/auth/login':
            return 200, {'access_token': '1' if payload['username'] == 'payer' else '2'}
        sender = int(token)
        if route == '/api/accounts/me':
            if self.mid_down and len(self.payments) == 1:
                raise urllib.error.URLError('down')
            balance = self.balances[sender]
            if self.final_drift and len(self.payments) == 2 and sender == 1:
                balance += Decimal('5')
            return 200, {'id': sender, 'balance': str(balance), 'status': 'ACTIVE'}
        if route.startswith('/api/transactions/'):
            tx_id=route.rsplit('/',1)[1]
            body=next((v for v in self.payments.values() if v['id']==tx_id), None)
            return (200,body) if body else (404,{})
        key = payload['idempotency_key']
        self.calls.append(key)
        if sender == 2 and self.refund_down:
            raise urllib.error.URLError('refund timeout')
        if key in self.payments:
            return 200, self.payments[key]
        amount = Decimal(payload['amount']);receiver = payload['receiver_account_id']
        self.balances[sender] -= amount;self.balances[receiver] += amount
        body = {'id': str(len(self.payments)+1), 'idempotency_key': key, 'status': 'SUCCESS',
                'sender_account_id': sender, 'receiver_account_id': receiver, 'amount': str(amount)}
        self.payments[key] = body
        if sender == 1 and self.lose_forward:
            self.lose_forward = False
            raise urllib.error.URLError('response lost after commit')
        return 201, body


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'probe.json'
        self.ledger = Ledger()
        self.probe = self.make()

    def make(self):
        return PaymentProbe('http://entry', ('payer','receiver'), ('secret','secret'), self.path, self.ledger)

    def test_success_two_real_operations_original_balances(self):
        result = self.probe.run(require_fresh=True)
        self.assertTrue(result['ok']);self.assertTrue(result['balances_restored'])
        self.assertEqual(self.ledger.balances,{1:Decimal('100'),2:Decimal('20')})
        self.assertEqual(len(self.ledger.payments),2)
        self.assertNotEqual(result['forward_id'],result['refund_id'])
        self.assertNotIn('secret',self.path.read_text())

    def test_lost_forward_response_does_not_double_debit(self):
        self.ledger.lose_forward=True
        with patch('payment_probe.time.sleep'):
            result=self.probe.run()
        self.assertTrue(result['ok']);self.assertEqual(len(self.ledger.payments),2)
        self.assertEqual(self.ledger.calls[0],self.ledger.calls[1])

    def test_refund_pending_survives_restart_and_is_not_fresh_proof(self):
        self.ledger.refund_down=True
        with patch('payment_probe.time.sleep'):
            first=self.probe.run()
        self.assertFalse(first['ok']);self.assertTrue(first['pending'])
        self.assertEqual(self.ledger.balances[1],Decimal('99'))
        self.ledger.refund_down=False
        resumed=self.make().run(require_fresh=True)
        self.assertFalse(resumed['ok']);self.assertTrue(resumed['compensated'])
        self.assertEqual(len(self.ledger.payments),2)
        fresh=self.make().run(require_fresh=True)
        self.assertTrue(fresh['ok']);self.assertEqual(len(self.ledger.payments),4)

    def test_mid_check_failure_still_returns_money(self):
        self.ledger.mid_down=True
        result=self.probe.run()
        self.assertFalse(result['ok']);self.assertTrue(result['compensated'])
        self.assertEqual(self.ledger.balances[1],Decimal('100'))

    def test_concurrent_balance_change_is_not_silently_reset(self):
        self.ledger.final_drift=True
        result=self.probe.run()
        self.assertFalse(result['ok']);self.assertTrue(result['compensated'])
        self.assertFalse(result['balances_restored'])

    def test_uses_new_keys_for_each_completed_cycle(self):
        a=self.probe.run();b=self.probe.run()
        self.assertTrue(a['ok'] and b['ok'])
        self.assertNotEqual(a['run_id'],b['run_id'])

    def test_changed_users_do_not_resume_old_payment(self):
        self.ledger.refund_down=True
        with patch('payment_probe.time.sleep'):
            self.probe.run()
        other=PaymentProbe('http://entry',('other','receiver'),('secret','secret'),self.path,self.ledger)
        self.assertFalse(other.run()['ok'])
        self.assertEqual(len(self.ledger.payments),1)

    def test_missing_forward_after_database_restore_prevents_wrong_refund(self):
        self.ledger.refund_down=True
        with patch('payment_probe.time.sleep'):
            self.probe.run()
        # Simuler une base restaurée avant le paiement aller.
        self.ledger.payments.clear()
        self.ledger.balances={1:Decimal('100'),2:Decimal('20')}
        self.ledger.refund_down=False
        result=self.make().run()
        self.assertFalse(result['ok'])
        self.assertEqual(self.ledger.balances[1],Decimal('100'))
        self.assertEqual(len(self.ledger.payments),0)

    def test_invalid_credentials_never_start_payment(self):
        self.probe.passwords=('','')
        self.assertFalse(self.probe.run()['ok']);self.assertEqual(len(self.ledger.payments),0)


if __name__ == '__main__':
    unittest.main()
