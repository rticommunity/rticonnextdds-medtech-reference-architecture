# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Check the canonical README's staged platform-tab conversion."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_builder", ROOT / "docs/site/build.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PlatformTabsTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_platform_content_and_shared_launch(self):
        self.assertNotIn('=== "Linux"', self.source)
        result = builder.platform_tabs(self.source)
        for name in ("Linux", "macOS", "Windows"):
            self.assertEqual(result.count(f'=== "{name}"'), 2)
        self.assertNotIn("<!-- platform-tabs:", result)
        self.assertEqual(result.count("python medtech.py up --scenario or-all --ui-mode native"), 1)
        self.assertIn("    source .venv/bin/activate", result)
        self.assertIn(r"    call .venv\Scripts\activate.bat", result)
        self.assertIn("docs/SETUP.md#linux-system-gtk-bindings", result)

    def test_missing_or_malformed_groups_fail(self):
        for source in (
            self.source.replace("<!-- platform-tabs:end -->", "", 1),
            self.source.replace("#### Windows", "#### Other", 1),
        ):
            with self.subTest(source=source[:60]), self.assertRaises(ValueError):
                builder.platform_tabs(source)


if __name__ == "__main__":
    unittest.main()
