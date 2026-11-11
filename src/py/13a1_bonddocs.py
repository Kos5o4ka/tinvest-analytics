# ═══════════════════ ссылки на документы выпуска (без обращения к сети) ═══════════════════


def bond_doc_links(isin, secid=None, inn=None):
    """Ссылки на раскрытие информации по выпуску. e-disclosure.ru закрыт для ботов, поэтому строим только ссылку
    на поиск по ИНН эмитента (без ИНН — по ISIN); страница выпуска на Мосбирже открывается по коду бумаги."""
    isin = (isin or "").strip().upper()
    secid = (secid or isin or "").strip().upper()
    inn = re.sub(r"\D", "", str(inn or ""))
    inn = inn if len(inn) in (10, 12) else ""
    q = inn or isin
    return {"inn": inn or None,
            "edisclosure": "https://www.e-disclosure.ru/poisk-po-kompaniyam?query=" + urllib.parse.quote(q) if q else None,
            "moex": "https://www.moex.com/ru/issue.aspx?code=" + urllib.parse.quote(secid) if secid else None}
