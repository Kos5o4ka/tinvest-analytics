"""Тесты шифрования резервных копий (AES-256-CTR + HMAC), восстановления и экспорта. Без сети."""
import base64
import io
import os
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
KEY = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")


class Aes(unittest.TestCase):
    def test_fips197_c3(self):
        k = bytes(range(32))
        rk = M.aes256_expand_key(k)
        ct = M.aes256_encrypt_block(rk, bytes.fromhex("00112233445566778899aabbccddeeff"))
        self.assertEqual(ct.hex(), "8ea2b7ca516745bfeafc49904b496089")

    def test_nist_sp800_38a_ctr_aes256(self):
        iv = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        pt = bytes.fromhex("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51"
                           "30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710")
        ct = bytes.fromhex("601ec313775789a5b7a7f504bbf3d228f443e3ca4d62b59aca84e990cacaf5c5"
                           "2b0930daa23de94ce87017ba2d84988ddfc9c58db67aada613c2dd08457941a6")
        self.assertEqual(M.aes256_ctr(KEY, iv, pt), ct)
        self.assertEqual(M.aes256_ctr(KEY, iv, ct), pt)

    def test_ctr_partial_block_and_counter_carry(self):
        iv = b"\xff" * 16
        data = bytes(range(37))
        self.assertEqual(M.aes256_ctr(KEY, iv, M.aes256_ctr(KEY, iv, data)), data)


class Crypt(unittest.TestCase):
    def test_roundtrip(self):
        data = os.urandom(100000) + b"tail"
        blob = M.encrypt_bytes("пароль-123", data, iters=2000)
        self.assertEqual(M.decrypt_bytes("пароль-123", blob), data)
        self.assertNotIn(data[:32], blob)

    def test_wrong_password(self):
        blob = M.encrypt_bytes("secret1", b"hello", iters=2000)
        with self.assertRaises(M.BackupError) as cm:
            M.decrypt_bytes("secret2", blob)
        self.assertIn("пароль", str(cm.exception).lower())

    def test_tamper_any_part(self):
        blob = bytearray(M.encrypt_bytes("secret1", b"x" * 100, iters=2000))
        for pos in (3, 9, 15, 30, 45, len(blob) - 40, len(blob) - 1):
            b2 = bytearray(blob)
            b2[pos] ^= 1
            with self.assertRaises(M.BackupError):
                M.decrypt_bytes("secret1", bytes(b2))

    def test_not_a_backup(self):
        with self.assertRaises(M.BackupError):
            M.decrypt_bytes("x", b"PK\x03\x04 not our file" * 5)

    def test_unique_salt_nonce(self):
        a, b = M.encrypt_bytes("secret1", b"same", iters=2000), M.encrypt_bytes("secret1", b"same", iters=2000)
        self.assertNotEqual(a, b)


class BackupFlow(unittest.TestCase):
    def setUp(self):
        M.store().put("probe", {"v": 1})
        self.dir = tempfile.mkdtemp(prefix="tinv_bk_")
        self.cfg = dict(M.load_config(), backup_dir=self.dir, backup_password="testpass1", backup_keep=2)

    def test_dir_check(self):
        self.assertTrue(M.backup_dir_check(self.dir)[0])
        self.assertFalse(M.backup_dir_check(os.path.join(self.dir, "nope"))[0])
        self.assertFalse(M.backup_dir_check("")[0])

    def test_plain_has_no_token_or_secrets(self):
        cfg = M.load_config()
        cfg["token"] = "t.SECRETTOKEN"
        cfg["backup_password"] = "pw-secret"
        M.save_config(cfg)
        try:
            z = zipfile.ZipFile(io.BytesIO(M.backup_plain()))
            text = z.read("config.json").decode()
            self.assertNotIn("SECRETTOKEN", text)
            self.assertNotIn("pw-secret", text)
            self.assertIn("data.db", z.namelist())
        finally:
            cfg["token"] = ""
            cfg["backup_password"] = ""
            M.save_config(cfg)

    def test_run_prune_and_restore(self):
        import time
        for i in range(3):
            M.encrypt_bytes  # noqa: B018
            name = "tinvest_backup_2020-01-0%d_000000%s" % (i + 1, M.BK_EXT)
            open(os.path.join(self.dir, name), "wb").write(b"x")
        open(os.path.join(self.dir, "mine.txt"), "w").write("keep me")
        st = M.run_backup(self.cfg)
        self.assertTrue(st["ok"])
        names = sorted(os.listdir(self.dir))
        self.assertIn("mine.txt", names)
        own = [n for n in names if M.BK_RE.match(n)]
        self.assertEqual(len(own), 2)
        self.assertIn(st["file"], own)
        blob = open(os.path.join(self.dir, st["file"]), "rb").read()
        # восстановление: подготовленная база появляется и проходит проверку
        b64 = base64.b64encode(blob).decode()
        with self.assertRaises(M.ApiError):
            M.api_backup_restore(dict(self.cfg), {"data": b64, "password": "wrong"})
        pend = M.DB_PATH + ".restore-pending"
        self.assertFalse(os.path.exists(pend))
        res = M.api_backup_restore(dict(self.cfg), {"data": b64, "password": "testpass1"})
        self.assertTrue(res["restart"])
        self.assertTrue(os.path.exists(pend))
        # подмена при открытии базы
        p2 = os.path.join(tempfile.mkdtemp(prefix="tinv_rs_"), "data.db")
        import shutil
        shutil.copy(pend, p2)
        shutil.copy(pend, p2 + ".restore-pending")
        s = M.Store(p2)
        self.assertEqual(s.get("probe"), {"v": 1})
        self.assertTrue(os.path.exists(p2 + ".before-restore"))
        self.assertFalse(os.path.exists(p2 + ".restore-pending"))
        os.remove(pend)

    def test_run_errors(self):
        with self.assertRaises(M.BackupError):
            M.run_backup(dict(self.cfg, backup_password=""))
        with self.assertRaises(M.BackupError):
            M.run_backup(dict(self.cfg, backup_dir=os.path.join(self.dir, "nope")))

    def test_password_not_in_public_config(self):
        self.assertIn("backup_password", M.SECRET_KEYS)

    def test_restore_garbage(self):
        with self.assertRaises(M.ApiError):
            M.api_backup_restore(dict(self.cfg), {"data": base64.b64encode(b"junk").decode(), "password": "x"})


class Export(unittest.TestCase):
    HDR = ["Дата", "Название", "Сумма"]
    ROWS = [["2026-03-05", "ОФЗ <26238> & Ко", 1234.5], ["2026-03-06", "Текст", None], [None, "x\x01y", 3]]

    def test_csv(self):
        b = M.export_csv(self.HDR, self.ROWS)
        self.assertTrue(b.startswith(b"\xef\xbb\xbf"))
        t = b.decode("utf-8-sig")
        self.assertIn("Дата;Название;Сумма", t)
        self.assertIn("1234,5", t)

    def test_xlsx_parses(self):
        b = M.export_xlsx(self.HDR, self.ROWS)
        z = zipfile.ZipFile(io.BytesIO(b))
        self.assertIsNone(z.testzip())
        for n in z.namelist():
            ET.fromstring(z.read(n))                    # все части — корректный XML
        for n in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/styles.xml"):
            self.assertIn(n, z.namelist())
        sh = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("<v>1234.5</v>", sh)
        self.assertIn('s="2"><v>46086</v>', sh)         # 2026-03-05 как дата (серийный номер)
        self.assertIn("&lt;26238&gt; &amp; Ко", sh)
        self.assertNotIn("\x01", sh)

    def test_col_letters(self):
        self.assertEqual([M._xl_col(i) for i in (0, 25, 26, 701, 702)], ["A", "Z", "AA", "ZZ", "AAA"])


if __name__ == "__main__":
    unittest.main()
