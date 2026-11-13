"""Clear All recovery contract: mocked runtime only, zero machine/G-code motion."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import cxm_native as native

ACK = native.CLEAR_ALL_ACK

class Store:
    def read(self):
        return {'revision': 'a'*64, 'migration_required': False}

class ClearAllRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.before = ({'protocol': 2, 'ready': 1, 'fault': 1, 'current_tool': 3},
                       {'running': 1, 'stop': 1, 'state': 'running'}, 'RELEASED')
        self.after = ({'protocol': 2, 'ready': 1, 'fault': 0, 'current_tool': -1},
                      {'running': 0, 'stop': 0, 'state': 'idle'}, 'RELEASED')

    def test_stuck_test_and_stale_t3_reset_only_when_empty(self):
        with patch.object(native, '_native_status', side_effect=[self.before, self.after]), \
             patch.object(native, '_rpc', side_effect=[{'state': 'ready'}, {}]) as rpc, \
             patch.object(native, 'MOVE_LOCK') as lock:
            lock.acquire.return_value = True
            result = native.clear_all(self.store, 'a'*64, ACK)
            self.assertTrue(result['cleared'])
            self.assertEqual((result['current_tool'], result['sensor'], result['fault']),(-1, 'RELEASED', 0))
            self.assertTrue(result['calibration_preserved'])
            self.assertTrue(result['no_motion'])
            self.assertEqual(rpc.call_count, 2)
            self.assertEqual(rpc.call_args_list[1].args,
                             ('/printer/gcode/script', {'script': 'CXM_RECOVER CONFIRM=EMPTY'}))
            lock.release.assert_called_once()

    def test_never_runs_recovery_when_sensor_pressed(self):
        attached = (self.before[0], self.before[1], 'PRESSED')
        with patch.object(native, '_native_status', return_value=attached), \
             patch.object(native, '_rpc') as rpc:
            with self.assertRaisesRegex(native.NativeError, 'sensor must read RELEASED'):
                native.clear_all(self.store, 'a'*64, ACK)
            rpc.assert_not_called()

    def test_rejects_missing_approval_and_revision_conflict(self):
        with patch.object(native, '_rpc') as rpc:
            with self.assertRaises(native.NativeError):
                native.clear_all(self.store, 'a'*64, 'I_IGNORE_TOOL_ON_CARRIAGE')
            with self.assertRaisesRegex(native.NativeError, 'configuration changed'):
                native.clear_all(self.store, 'b'*64, ACK)
            rpc.assert_not_called()

    def test_refuses_when_unsynced_or_recovery_not_verified(self):
        not_ready = ({'protocol': 2,'ready': 0}, self.before[1], 'RELEASED')
        with patch.object(native, '_native_status', return_value=not_ready), \
             patch.object(native, '_rpc') as rpc:
            with self.assertRaisesRegex(native.NativeError,'not synchronized'):
                native.clear_all(self.store, 'a'*64, ACK)
            rpc.assert_not_called()
        bad_after = ({'ready': 1, 'fault': 0, 'current_tool': 3},
                     {'running': 0, 'stop': 0, 'state': 'idle'}, 'RELEASED')
        with patch.object(native, '_native_status', side_effect=[self.before, bad_after]), \
             patch.object(native, '_rpc', side_effect=[{'state':'ready'}, {}]), \
             patch.object(native, 'MOVE_LOCK') as lock:
            lock.acquire.return_value = True
            with self.assertRaisesRegex(native.NativeError,'not fully verified'):
                native.clear_all(self.store, 'a'*64, ACK)
            lock.release.assert_called_once()

if __name__ == '__main__':
    unittest.main()
