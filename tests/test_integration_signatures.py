import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.integrations import compute_hmac_sha256_hex, compute_sha256_hex, verify_hmac_sha256_hex

class SignatureHelpersTest(unittest.TestCase):
    def test_hmac_sha256_verification_accepts_prefixed_signature(self) -> None:
        payload = b'{"event":"ticket.updated"}'
        secret = "super-secret"
        signature = compute_hmac_sha256_hex(secret, payload)

        self.assertTrue(verify_hmac_sha256_hex(secret, payload, "sha256=" + signature))
        self.assertTrue(verify_hmac_sha256_hex(secret, payload, signature, prefix=""))
        self.assertFalse(verify_hmac_sha256_hex(secret, payload, "sha256=deadbeef"))

    def test_sha256_digest_is_stable(self) -> None:
        self.assertEqual(
            compute_sha256_hex("AgentHub"),
            "c1cfba5b2014bf9ed601c64413806399e3148fbb6d440b3a86e1da380becb18f",
        )
