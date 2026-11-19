"""Дополнительные библиотеки: загрузка колеса по требованию с проверкой SHA256 (src/py/02b_vendor.py).
Сеть не используется: колёса собираются в тесте, загрузка подменяется."""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from tests._load import load

T = load()


def wheel(pkg, body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("%s/__init__.py" % pkg, body)
        z.writestr("%s-1.0.dist-info/METADATA" % pkg, "Name: %s\nVersion: 1.0\n" % pkg)
    return buf.getvalue()


def entry(pkg, data, **kw):
    e = {"name": pkg, "version": "1.0", "file": "%s-1.0-py3-none-any.whl" % pkg, "sha256": hashlib.sha256(data).hexdigest(),
         "size": len(data), "url": "https://files.pythonhosted.org/x/%s.whl" % pkg, "python": [3, 8], "only_below": None, "requires": []}
    e.update(kw)
    return e


class VendorBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        n = self.id().rsplit(".", 1)[-1].replace("test_", "")[:20]
        self.pkg, self.dep = "tavend_%s" % n, "tavdep_%s" % n
        self.dep_data = wheel(self.dep, "DEP = 7\n")
        self.data = wheel(self.pkg, "from %s import DEP\nVALUE = 35 + DEP\n" % self.dep)
        self.lock = [entry(self.dep, self.dep_data), entry(self.pkg, self.data, requires=[self.dep])]
        self.served = {}
        for e, d in ((self.lock[0], self.dep_data), (self.lock[1], self.data)):
            self.served[e["url"]] = d
        self.calls = []

        def get(url, limit, timeout):
            self.calls.append(url)
            if url not in self.served:
                raise OSError("нет сети")
            d = self.served[url]
            if len(d) > limit:
                raise ValueError("файл больше ожидаемого")
            return d
        self.p = [mock.patch.object(T, "VENDOR_DIR", self.tmp), mock.patch.object(T, "VENDOR_LOCK", self.lock),
                  mock.patch.object(T, "_vendor_get", get), mock.patch.dict(T._vendor_ok, {}, clear=True)]
        for p in self.p:
            p.start()
        self.path0 = list(sys.path)

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        sys.path[:] = self.path0
        for m in [k for k in sys.modules if k.startswith(("tavend_", "tavdep_"))]:
            del sys.modules[m]
        shutil.rmtree(self.tmp, ignore_errors=True)


class VendorImport(VendorBase):
    def test_downloads_verifies_and_imports_with_dependency(self):
        self.assertFalse(T.vendor_available(self.pkg))
        m = T.vendor_import(self.pkg)
        self.assertEqual(m.VALUE, 42)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, self.lock[1]["file"])))
        self.assertTrue(T.vendor_available(self.pkg))
        n = len(self.calls)
        T.vendor_import(self.pkg)                     # второй раз — без сети
        self.assertEqual(len(self.calls), n)

    def test_tampered_download_rejected_everywhere(self):
        for k in self.served:
            self.served[k] = wheel(self.pkg, "VALUE = 'evil'\n") if self.pkg in k else self.served[k]
        gh = T.VENDOR_GH % (T.APP_VERSION, self.lock[1]["file"])
        self.served[gh] = wheel(self.pkg, "VALUE = 'evil2'\n")
        with self.assertRaises(T.ApiError) as cm:
            T.vendor_import(self.pkg)
        self.assertIn("контрольная сумма", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, self.lock[1]["file"])))

    def test_falls_back_to_github_release(self):
        url = self.lock[1]["url"]
        good = self.served.pop(url)
        self.served[T.VENDOR_GH % (T.APP_VERSION, self.lock[1]["file"])] = good
        self.assertEqual(T.vendor_import(self.pkg).VALUE, 42)

    def test_corrupted_file_on_disk_is_replaced(self):
        T.vendor_import(self.pkg)
        path = os.path.join(self.tmp, self.lock[1]["file"])
        with open(path, "wb") as f:
            f.write(b"garbage")
        T._vendor_ok.clear()
        self.assertFalse(T.vendor_available(self.pkg))
        self.assertFalse(os.path.exists(path))        # испорченный файл удалён при проверке
        T.vendor_import(self.pkg)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_no_download_mode(self):
        with self.assertRaises(T.ApiError):
            T.vendor_import(self.pkg, download=False)
        self.assertEqual(self.calls, [])

    def test_oversized_response_rejected(self):
        self.served[self.lock[1]["url"]] = self.data + b"x" * 5000
        with self.assertRaises(T.ApiError):
            T.vendor_import(self.pkg)

    def test_old_python_gives_clear_message(self):
        self.lock[1]["python"] = [9, 9]
        with self.assertRaises(T.ApiError) as cm:
            T.vendor_import(self.pkg)
        self.assertIn("Python 9.9", str(cm.exception))
        self.assertEqual(self.calls, [])

    def test_backport_skipped_on_new_python(self):
        self.lock[0]["only_below"] = [3, 0]           # «бэкпорт» не нужен ни на одной версии
        self.lock[1]["requires"] = [self.dep]
        self.served[self.lock[1]["url"]] = self.data = wheel(self.pkg, "VALUE = 1\n")
        self.lock[1].update(sha256=hashlib.sha256(self.data).hexdigest(), size=len(self.data))
        self.assertEqual(T.vendor_import(self.pkg).VALUE, 1)
        self.assertNotIn(self.lock[0]["url"], self.calls)

    def test_cleanup_removes_old_versions(self):
        old = os.path.join(self.tmp, "%s-0.9-py3-none-any.whl" % self.pkg)
        with open(old, "wb") as f:
            f.write(b"old")
        T.vendor_import(self.pkg)
        self.assertFalse(os.path.exists(old))

    def test_status(self):
        st = {x["name"]: x for x in T.vendor_status()}
        self.assertFalse(st[self.pkg]["installed"])
        T.vendor_import(self.pkg)
        st = {x["name"]: x for x in T.vendor_status()}
        self.assertTrue(st[self.pkg]["installed"] and st[self.dep]["installed"])

    def test_unknown_library(self):
        with self.assertRaises(T.ApiError):
            T.vendor_import("nope_not_in_lock")


class VendorLockFile(unittest.TestCase):
    def test_lock_matches_vendor_txt_and_only_pure_python(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(root, "packaging", "vendor_lock.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for e in T.VENDOR_LOCK:
            self.assertRegex(e["file"], r"-(py3|py2\.py3)-none-any\.whl$")
            self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(e["url"].startswith("https://files.pythonhosted.org/"))


if __name__ == "__main__":
    unittest.main()
