"""Moonraker timeout policy: per-stream override only; no automatic retry."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_lineux import _rpc,MeasurementError
from cxm_multi import STREAM_READ_TIMEOUT_S

class TimeoutTests(unittest.TestCase):
    def test_default_short_get_and_standard_post_are_unchanged(self):
        with (patch('cxm_lineux.urllib.request.urlopen') as openurl,
              patch('cxm_lineux.json.load',return_value={'result':{'ok':True}})):
            self.assertEqual(_rpc('/printer/info')['ok'],True)
            self.assertEqual(openurl.call_args.kwargs['timeout'],4)
            self.assertEqual(_rpc('/printer/gcode/script',{'script':'M400'})['ok'],True)
            self.assertEqual(openurl.call_args.kwargs['timeout'],125)

    def test_only_native_stream_explicitly_has_longer_bounded_timeout(self):
        with (patch('cxm_lineux.urllib.request.urlopen') as openurl,
              patch('cxm_lineux.json.load',return_value={'result':{}})):
            _rpc('/printer/gcode/script',{'script':'M400'},
                 timeout_s=STREAM_READ_TIMEOUT_S)
            self.assertEqual(openurl.call_args.kwargs['timeout'],600)
        for invalid in (True,False,0,-1,601,'600',float('nan')):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    _rpc('/printer/gcode/script',{'script':'M400'},
                         timeout_s=invalid)

    def test_timeout_is_uncertain_failure_and_never_retried(self):
        with patch('cxm_lineux.urllib.request.urlopen',
                   side_effect=TimeoutError('timed out')) as openurl:
            with self.assertRaisesRegex(MeasurementError,'timed out'):
                _rpc('/printer/gcode/script',{'script':'M400'},
                     timeout_s=STREAM_READ_TIMEOUT_S)
            self.assertEqual(openurl.call_count,1)

if __name__=='__main__':unittest.main()
