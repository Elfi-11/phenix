"""Tests sans réseau, sans Docker et sans action Ansible réelle."""
import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from remediation import moteur_ml as m


def alert(key='event-1',ip='192.0.2.50'):
    return {'detection_id':key,'loki_timestamp_ns':'900000000000','observed_at':'2026-10-21T13:00:00Z',
            'event_type':'ML_ANOMALY_DETECTED','severity':'CRITICAL','source':'ML','target_service':'backend',
            'description':'Test SQL ML','ip':ip,'peer_ip':'172.26.0.1','score':.9,'detection_kind':'sql_injection','threshold':.1}

class MoteurTests(unittest.TestCase):
    def test_event_dedup_and_one_pending_per_ip(self):
        state=m.fresh_state(1000*m.NS)
        m.enqueue(state,[alert(),alert('event-2'),alert('event-3','192.0.2.51')],1000*m.NS)
        self.assertEqual(len(state['pending']),2)
        m.enqueue(state,[alert()],1000*m.NS)
        self.assertEqual(len(state['pending']),2)

    def test_observation_calls_no_api_or_actions(self):
        state=m.fresh_state(1000*m.NS)
        with patch.object(m.time,'time_ns',return_value=1000*m.NS), \
             patch.object(m,'detecter_alertes',return_value={'scanned':1,'alerts':[alert()]}), \
             patch.object(m,'get_token') as auth,patch.object(m,'action_ansible') as action, \
             patch.object(m,'save_state') as save,contextlib.redirect_stdout(io.StringIO()):
            m.cycle(state)
            auth.assert_not_called();action.assert_not_called();save.assert_not_called()
        self.assertIn('event-1',state['seen'])

    def test_collection_error_does_not_advance_cursor(self):
        state=m.fresh_state(1000*m.NS);before=state['cursor_ns']
        with patch.object(m.time,'time_ns',return_value=1000*m.NS),patch.object(m,'detecter_alertes',side_effect=RuntimeError('down')):
            with self.assertRaises(RuntimeError):m.cycle(state)
        self.assertEqual(state['cursor_ns'],before)

    def test_verify_failure_then_reuse_incident(self):
        entry={'alert':alert(),'incident_id':None}
        with patch.object(m,'ouvrir_incident',return_value=7) as opened, \
             patch.object(m,'resoudre_incident') as closed,patch.object(m,'protected_reason',return_value=None), \
             patch.object(m,'action_ansible',side_effect=[(True,''),(False,'HTTP KO'),(True,''),(True,'')]) as actions, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.traiter('token',entry,'http://host/health',lambda:None),'retry')
            closed.assert_not_called()
            self.assertEqual(m.traiter('token',entry,'http://host/health',lambda:None),'resolved')
            opened.assert_called_once();closed.assert_called_once()
            self.assertEqual(actions.call_args_list[0].kwargs['reason'],'sql_injection')
            self.assertEqual(actions.call_args_list[1].kwargs['check_url'],'http://host/health')

    def test_loopback_incident_stays_open_without_block(self):
        entry={'alert':alert(ip='127.0.0.1'),'incident_id':None}
        with patch.object(m,'ouvrir_incident',return_value=8),patch.object(m,'action_ansible') as action, \
             patch.object(m,'resoudre_incident') as closed,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.traiter('token',entry,'http://host/health',lambda:None),'protected')
            action.assert_not_called();closed.assert_not_called()

    def test_three_failures_keep_failure_and_stop_retrying(self):
        state=m.fresh_state(1000*m.NS);m.enqueue(state,[alert()],1000*m.NS)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'get_token',return_value='token'), \
             patch.object(m,'traiter',return_value='retry') as process,contextlib.redirect_stdout(io.StringIO()):
            path=Path(tmp)/'state.json'
            for now in [1000,1031,1062]:m.process_pending(state,'http://host/health',path,now*m.NS)
            self.assertEqual(process.call_count,3)
            self.assertEqual(state['pending'],{})
            self.assertEqual(state['last_incident']['192.0.2.50']['result'],'failed')
            restored=json.loads(path.read_text());self.assertEqual(restored,state)

    def test_dynamic_wsl_url(self):
        with patch.dict(m.os.environ,{},clear=True),patch.object(m.platform,'system',return_value='Windows'), \
             patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout='default via 172.19.64.1 dev eth0\n')):
            self.assertEqual(m.check_url(),'http://172.19.64.1:8080/health')

    def test_both_models_are_readonly_and_kind_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model.joblib';model.write_bytes(b'placeholder')
            with patch.object(m,'SQL_MODEL',model),patch.object(m,'BRUTE_MODEL',model), \
                 patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"scanned":0,"alerts":[]}',stderr='')) as run:
                self.assertEqual(m.detecter_alertes(1,2)['alerts'],[])
                args=run.call_args.args[0]
                mounts=[args[i+1] for i,x in enumerate(args) if x=='--mount']
                self.assertEqual(len(mounts),2)
                self.assertTrue(all('readonly' in x for x in mounts))

    def test_two_families_same_ip_share_one_pending_action(self):
        state=m.fresh_state(1000*m.NS)
        a=alert();b=alert('brute-event');b['detection_kind']='bruteforce'
        m.enqueue(state,[a,b],1000*m.NS)
        self.assertEqual(len(state['pending']),1)
        self.assertEqual(len(state['seen']),2)

    def test_bruteforce_reason_routes_to_ansible(self):
        a=alert();a['detection_kind']='bruteforce'
        entry={'alert':a,'incident_id':None}
        with patch.object(m,'ouvrir_incident',return_value=9),patch.object(m,'protected_reason',return_value=None), \
             patch.object(m,'action_ansible',return_value=(True,'')) as action, \
             patch.object(m,'resoudre_incident'),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.traiter('token',entry,'http://host/health',lambda:None),'resolved')
        self.assertEqual(action.call_args_list[0].kwargs['reason'],'bruteforce')

if __name__=='__main__':unittest.main()
