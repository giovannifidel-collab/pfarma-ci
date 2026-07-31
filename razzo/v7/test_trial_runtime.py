import inspect
import unittest

import razzo.v7.trial_runtime as runtime


class TrialRuntimeSandboxTests(unittest.TestCase):
    def test_product_worker_does_not_enable_legacy_landlock(self):
        source = inspect.getsource(runtime)
        self.assertNotIn("use_legacy_landlock", source)
        self.assertNotIn("install_codex_worker_wrapper", source)


if __name__ == "__main__":
    unittest.main()
