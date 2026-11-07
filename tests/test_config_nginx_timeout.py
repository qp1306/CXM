"""Regression for the CXM Nginx long-running motion API gateway upgrade."""
import importlib.util
from pathlib import Path
import unittest

file = Path(__file__).resolve().parents[1] / 'scripts' / 'cxm_config_install.py'
spec = importlib.util.spec_from_file_location('cxm_config_install', file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NginxTimeoutTests(unittest.TestCase):
    def test_actual_proxy_timeout_exceeds_backend_motion_wait(self):
        self.assertIn('proxy_read_timeout 150s;', module.PROXY)
        self.assertIn('proxy_read_timeout 6s;', module.LEGACY_PROXY)
        self.assertNotIn('proxy_read_timeout 6s;', module.PROXY)

    def test_upgrade_preserves_other_nginx_locations_and_permissions(self):
        old = '# unrelated site metadata\n' + module.LEGACY_PROXY + '\nlocation /cxm/ { alias /data/cxm/; }\n'
        upgraded = module.updated_proxy_snippet(old)
        self.assertEqual(upgraded, old.replace(module.LEGACY_PROXY.strip(),module.PROXY.strip()))
        self.assertIn('allow 10.0.0.0/8;',upgraded)
        self.assertIn('location /cxm/ { alias /data/cxm/; }',upgraded)
        self.assertEqual(upgraded.count('location /cxm/api/'),1)

    def test_safe_idempotence(self):
        current = module.PROXY + '\nlocation /other/ { return 200; }\n'
        self.assertEqual(module.updated_proxy_snippet(current),current)

    def test_older_snippet_without_api_gets_new_route(self):
        current='location /cxm/ { alias /var/www/cxm/; }\n'
        out=module.updated_proxy_snippet(current)
        self.assertIn(module.PROXY.strip(),out)
        self.assertTrue(out.endswith(current))

    def test_unknown_or_duplicate_api_does_not_get_overwritten(self):
        for current in [
            'location /cxm/api/ { proxy_pass http://private.example/; }',
            module.LEGACY_PROXY+module.LEGACY_PROXY,
            module.PROXY+module.PROXY,
        ]:
            with self.subTest(current=current[:32]):
                with self.assertRaisesRegex(RuntimeError,'Unrecognised or duplicated'):
                    module.updated_proxy_snippet(current)

if __name__=='__main__':
    unittest.main()
