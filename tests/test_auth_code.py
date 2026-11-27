"""Вход в один клик: код подтверждения (сверяется в программе и в боте), без сети."""
import hashlib
import hmac
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
VERIFIER, NONCE = "v" * 43, "n" * 24
VECTOR = "3354"             # тот же набор значений проверяется в тестах бота: коды обязаны совпадать


class AuthCode(unittest.TestCase):
    def test_vector_and_shape(self):
        self.assertEqual(M.auth_confirm_code(VERIFIER, NONCE), VECTOR)
        self.assertRegex(M.auth_confirm_code("x" * 43, "y" * 24), r"^\d{4}$")

    def test_depends_on_both_values(self):
        self.assertNotEqual(M.auth_confirm_code(VERIFIER, NONCE), M.auth_confirm_code(VERIFIER + "a", NONCE))
        self.assertNotEqual(M.auth_confirm_code(VERIFIER, NONCE), M.auth_confirm_code(VERIFIER, NONCE + "a"))
        codes = {M.auth_confirm_code("v%042d" % i, NONCE) for i in range(200)}
        self.assertGreater(len(codes), 150)                       # код не константа и разбросан равномерно

    def test_start_returns_code_matching_stored_challenge(self):
        seen = {}
        real = M._auth_link_post

        def fake(path, body):
            seen.update(body)
            return 200, {"ok": True, "ttl": 120}
        M._auth_link_post = fake
        try:
            r = M.auth_link_start({}, {})
        finally:
            M._auth_link_post = real
        # бот знает только nonce и challenge (хеш verifier) и обязан получить тот же код
        h = hmac.new(bytes.fromhex(seen["challenge"]), b"tinvest-auth-code|" + seen["nonce"].encode(), hashlib.sha256).digest()
        self.assertEqual(r["code"], "%04d" % (int.from_bytes(h[:4], "big") % 10000))
        self.assertNotIn(M._auth_link["verifier"], json_dump(r))


def json_dump(x):
    import json
    return json.dumps(x)


if __name__ == "__main__":
    unittest.main()
