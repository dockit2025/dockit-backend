from src.core.quantity import extract_qty

def test_explicit_meter():
    q,u,default = extract_qty("dra 12 meter kabel")
    assert (q,u,default) == (12.0,"meter",False)

def test_default_when_missing():
    q,u,default = extract_qty("montera dosa")
    assert default is True and q == 1.0
