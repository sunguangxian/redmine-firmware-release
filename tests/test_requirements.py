import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RequirementsTest(unittest.TestCase):
    def test_backend_dependencies_have_upper_bounds(self):
        requirements = ROOT / "requirements.txt"
        violations = []
        for raw in requirements.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ">=" not in line or "<" not in line:
                violations.append(line)

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
