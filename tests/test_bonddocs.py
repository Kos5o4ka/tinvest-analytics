"""Ссылки на документы выпуска: ИНН -> e-disclosure, код -> Мосбиржа (без сети)."""
import unittest

from tests._load import load

T = load()


class BondDocLinks(unittest.TestCase):
    def test_inn(self):
        d = T.bond_doc_links("ru000a104jq3", "RU000A104JQ3", "7714964716")
        self.assertEqual(d["inn"], "7714964716")
        self.assertEqual(d["edisclosure"], "https://www.e-disclosure.ru/poisk-po-kompaniyam?query=7714964716")
        self.assertEqual(d["moex"], "https://www.moex.com/ru/issue.aspx?code=RU000A104JQ3")

    def test_bad_inn_falls_back_to_isin(self):
        d = T.bond_doc_links("SU26238RMFS4", "SU26238RMFS4", "12 3")
        self.assertIsNone(d["inn"])
        self.assertTrue(d["edisclosure"].endswith("query=SU26238RMFS4"))

    def test_inn_with_spaces_and_secid_default(self):
        d = T.bond_doc_links("RU000A104JQ3", None, " 7714 964716 ")
        self.assertEqual(d["inn"], "7714964716")
        self.assertIn("code=RU000A104JQ3", d["moex"])


if __name__ == "__main__":
    unittest.main()
