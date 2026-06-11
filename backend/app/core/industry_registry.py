"""Single source of truth for industry-name → Lixinger endpoint kind."""

from typing import Optional

_BANK_INDUSTRIES = {"银行"}
_INSURANCE_INDUSTRIES = {"保险", "保险Ⅱ"}
_SECURITY_INDUSTRIES = {"证券", "证券Ⅱ"}
_OTHER_FINANCIAL_INDUSTRIES = {"多元金融", "其他金融"}

_KIND_BY_INDUSTRY: dict[str, str] = {}
for _name in _BANK_INDUSTRIES:
    _KIND_BY_INDUSTRY[_name] = "bank"
for _name in _INSURANCE_INDUSTRIES:
    _KIND_BY_INDUSTRY[_name] = "insurance"
for _name in _SECURITY_INDUSTRIES:
    _KIND_BY_INDUSTRY[_name] = "security"
for _name in _OTHER_FINANCIAL_INDUSTRIES:
    _KIND_BY_INDUSTRY[_name] = "other_financial"


def industry_kind(industry: Optional[str]) -> str:
    """Return the Lixinger financial endpoint kind for an industry name.

    One of: 'bank' | 'insurance' | 'security' | 'other_financial' | 'non_financial'.
    Empty / unknown → 'non_financial'.
    """
    if not industry:
        return "non_financial"
    return _KIND_BY_INDUSTRY.get(industry, "non_financial")
