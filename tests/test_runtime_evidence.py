"""CXM V0.9.0: restart evidence must be read-only and never fabricate proof."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_service import parse_proc_start_ticks,runtime_evidence

def proc_stat(pid,ticks):
    fields=['S']+['0']*35
    fields[19]=str(ticks)
    return f'{pid} (klippy host app) '+' '.join(fields)

class RuntimeProof(unittest.TestCase):
    def test_linux_proc_parser_handles_spaced_comm(self):
        self.assertEqual(parse_proc_start_ticks(proc_stat(402,987654),402),987654)
        with self.assertRaises(ValueError):
            parse_proc_start_ticks(proc_stat(402,9),403)
        with self.assertRaises(ValueError):
            parse_proc_start_ticks('402 (klippy) S',402)

    def test_process_identity_is_stable_and_changes_on_relaunch(self):
        pid=402
        boot='11111111-1111-1111-1111-111111111111'
        def get(ticks):
            def fake_read(self,encoding=None):
                if str(self)==f'/proc/{pid}/stat':
                    return proc_stat(pid,ticks)
                if str(self)=='/proc/sys/kernel/random/boot_id':
                    return boot
                raise FileNotFoundError(str(self))
            response={'result':{'state':'ready','process_id':pid}}
            with patch('cxm_service.urllib.request.urlopen',
                       return_value=io.BytesIO(json.dumps(response).encode())):
                with patch('cxm_service.Path.read_text',new=fake_read):
                    return runtime_evidence()
        a=get(912345);b=get(912345);c=get(912346)
        self.assertTrue(a['available'])
        self.assertEqual(a['identity'],b['identity'])
        self.assertNotEqual(a['identity'],c['identity'])
        self.assertFalse(a['active_in_klipper'])
        self.assertNotIn('process_id',a)
        self.assertIn('does not prove runtime macro',a['limitation'])

    def test_missing_pid_fails_closed(self):
        response={'result':{'state':'ready'}}
        with patch('cxm_service.urllib.request.urlopen',
                   return_value=io.BytesIO(json.dumps(response).encode())):
            result=runtime_evidence()
        self.assertFalse(result['available'])
        self.assertIsNone(result['identity'])
        self.assertFalse(result['active_in_klipper'])
        self.assertIn('process_id',result['reason'])

if __name__=='__main__':
    unittest.main()
