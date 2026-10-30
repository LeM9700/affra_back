import pytest

from app.services.phone import InvalidPhoneError, format_french_phone, normalize_french_phone


@pytest.mark.parametrize(
    "raw",
    ["06 12 34 56 78", "0612345678", "06.12.34.56.78", "06-12-34-56-78", "+33 6 12 34 56 78", "+33612345678",
     "0033 6 12 34 56 78", "(06) 12 34 56 78"],
)
def test_all_common_spellings_give_the_same_e164(raw):
    assert normalize_french_phone(raw) == "+33612345678"


@pytest.mark.parametrize("raw", ["04 66 00 00 00", "09 70 00 00 00", "07 66 30 46 87"])
def test_landlines_and_mobiles_are_accepted(raw):
    assert normalize_french_phone(raw).startswith("+33")


@pytest.mark.parametrize(
    "raw", ["", "   ", "06 12 34 56", "06 12 34 56 78 90", "08 00 00 00 00", "00 00 00 00 00", "+44 20 7946 0958",
            "0044 20 7946 0958", "06 12 34 56 7a", "<script>"],
)
def test_invalid_or_foreign_numbers_are_refused(raw):
    with pytest.raises(InvalidPhoneError):
        normalize_french_phone(raw)


def test_display_format():
    assert format_french_phone("+33612345678") == "06 12 34 56 78"
    assert format_french_phone(None) == "—"
    assert format_french_phone("+4420") == "+4420"
