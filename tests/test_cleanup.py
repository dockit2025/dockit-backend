from src.core.cleanup import cleanup

def test_money_groups_to_narrow_nbsp():
    html = "<div>1 450,00 kr</div>"
    out = cleanup(html)
    assert "1&#8239;450,00 kr" in out

def test_mm2_to_mm2_sup():
    out = cleanup("<p>10 mm2 kabel</p>")
    assert "10 mm²" in out
