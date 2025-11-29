from src.core.validate import validate

def test_validator_basic_pass():
    html = """
    <div id="supplier-box">Dockit<br>Org.nr: 5599991234<br>info@dockit.se</div>
    <div id="client-box">Poseidon<br>Org.nr: 5560342462<br>kontakt@poseidon.se</div>
    <div id="totals-box">
      <div class="line"><span>Material</span><span>11&#8239;670,00 kr</span></div>
      <div class="line"><span>Arbete (3,60 h)</span><span>9&#8239;200,00 kr</span></div>
      <div class="line"><span>Delsumma (exkl. moms)</span><span>20&#8239;870,00 kr</span></div>
      <div class="line"><span>Moms 25&nbsp;%</span><span>5&#8239;217,50 kr</span></div>
      <div class="line total"><span>Totalsumma (inkl. moms)</span><span>26&#8239;087,50 kr</span></div>
    </div>
    <div id="meta-box">Datum: 2025–11–03</div>
    <table><thead><tr>
      <th>Arbetsmoment</th><th>Moment/Typ/Sort</th><th>Underlag/Variant</th><th>Enhet</th><th>Tid</th><th>À-pris</th><th>Radsumma</th>
    </tr></thead></table>
    <table><thead><tr>
      <th>Artikel</th><th>Benämning</th><th>Enhet</th><th>Antal</th><th>À-pris</th><th>Radsumma</th><th>Lev.</th>
    </tr></thead></table>
    """
    rep = validate(html)
    assert "[FAIL]" not in rep.splitlines()[0]  # första raden ska vara PASS för templatemarkörer
