from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_ACTIVITY = (
    ROOT
    / "04_android"
    / "visionflow-dji-bridge"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "visionflow"
    / "dji"
    / "bridge"
    / "MainActivity.kt"
)


class Phase3DjiAndroidSecretInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.bridge_field = self.source.split(
            "bridgeKeyInput = addField(",
            maxsplit=1,
        )[1].split("\n\n        val actions", maxsplit=1)[0]

    def test_bridge_key_uses_explicit_password_transformation(self) -> None:
        self.assertIn(
            "import android.text.method.PasswordTransformationMethod",
            self.source,
        )
        self.assertIn(
            "InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD",
            self.bridge_field,
        )
        self.assertIn(
            "transformationMethod = PasswordTransformationMethod.getInstance()",
            self.bridge_field,
        )

    def test_activity_preserves_screen_and_autofill_secret_guards(self) -> None:
        self.assertIn(
            "window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)",
            self.source,
        )
        self.assertIn(
            "IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS",
            self.bridge_field,
        )
        self.assertGreaterEqual(self.source.count('bridgeKeyInput.setText("")'), 3)


if __name__ == "__main__":
    unittest.main()
