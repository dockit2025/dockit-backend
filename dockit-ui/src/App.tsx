import { useEffect, useRef, useState } from "react";
import "./print.css";

type LineKind = "work" | "material";
interface QuoteLineInput { kind: LineKind; description: string; qty: number; unit_price_sek: number; }
interface DraftRequest { customer_name: string; customer_email: string; job_summary: string; apply_rot: boolean; lines: QuoteLineInput[]; }
interface DraftResponse {
  title: string; subtotal_sek: number; rot_discount_sek: number; total_sek: number;
  lines: Array<{ kind: LineKind; description: string; qty: number; unit_price_sek: number; line_total_sek?: number; }>;
}
interface SaveResponse { id: number | string; title?: string; subtotal_sek?: number; rot_discount_sek?: number; total_sek?: number; }

const API_BASE = "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState("Okänt");
  const [loadingHealth, setLoadingHealth] = useState(false);

  const [customerName, setCustomerName] = useState("Dockit El & Data AB");
  const [customerEmail, setCustomerEmail] = useState("info@dockit.se");
  const [jobSummary, setJobSummary] = useState("Installation av belysning och uttag i hall");
  const [applyRot, setApplyRot] = useState(true);
  const [lines, setLines] = useState<QuoteLineInput[]>([
    { kind: "work", description: "Elmontör, installation och montering", qty: 8, unit_price_sek: 640 },
    { kind: "material", description: "LED-armatur infälld", qty: 4, unit_price_sek: 390 },
  ]);

  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [savedId, setSavedId] = useState<number | string | null>(null);
  const [submittingDraft, setSubmittingDraft] = useState(false);
  const [savingQuote, setSavingQuote] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hämta sparad offert
  const [fetchId, setFetchId] = useState("");
  const [fetchedQuote, setFetchedQuote] = useState<any>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const printRef = useRef<HTMLDivElement>(null);

  const fetchHealth = async () => {
    try {
      setLoadingHealth(true);
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setHealth(JSON.stringify(data));
    } catch {
      setHealth("Fel vid hämtning av /health");
    } finally {
      setLoadingHealth(false);
    }
  };
  useEffect(() => { fetchHealth(); }, []);

  const updateLine = (i: number, patch: Partial<QuoteLineInput>) => setLines(p => p.map((l, idx) => idx===i ? {...l, ...patch} : l));
  const addLine = () => setLines(p => [...p, { kind:"work", description:"", qty:1, unit_price_sek:0 }]);
  const removeLine = (i: number) => setLines(p => p.filter((_, idx) => idx !== i));

  const toPayload = (): DraftRequest => ({
    customer_name: customerName.trim(),
    customer_email: customerEmail.trim(),
    job_summary: jobSummary.trim(),
    apply_rot: applyRot,
    lines: lines.map(l => ({ kind:l.kind, description:l.description.trim(), qty:Number(l.qty)||0, unit_price_sek:Number(l.unit_price_sek)||0 })),
  });

  const validate = (): string | null => {
    if (!customerName.trim()) return "Kundnamn saknas.";
    if (!customerEmail.trim()) return "E-post saknas.";
    if (!jobSummary.trim()) return "Jobbbeskrivning saknas.";
    if (lines.length === 0) return "Minst en rad krävs.";
    for (let i=0;i<lines.length;i++){
      const l=lines[i];
      if(!l.description.trim()) return `Rad ${i+1}: beskrivning saknas.`;
      if(!["work","material"].includes(l.kind)) return `Rad ${i+1}: ogiltig typ.`;
      if(Number(l.qty)<=0) return `Rad ${i+1}: antal måste vara > 0.`;
      if(Number(l.unit_price_sek)<0) return `Rad ${i+1}: à-pris kan inte vara negativt.`;
    }
    return null;
  };

  const onDraft = async () => {
    setError(null); setDraft(null); setSavedId(null);
    const v = validate(); if (v) { setError(v); return; }
    setSubmittingDraft(true);
    try {
      const res = await fetch(`${API_BASE}/quotes/draft`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(toPayload()) });
      if(!res.ok) throw new Error((await res.text()) || "Misslyckades att beräkna offert.");
      const data: DraftResponse = await res.json();
      setDraft(data);
    } catch(e:any){ setError(e.message || "Ett fel inträffade vid beräkning."); }
    finally { setSubmittingDraft(false); }
  };

  const onSave = async () => {
    setError(null); setSavedId(null);
    const v = validate(); if (v) { setError(v); return; }
    setSavingQuote(true);
    try {
      const res = await fetch(`${API_BASE}/quotes`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(toPayload()) });
      if(!res.ok) throw new Error((await res.text()) || "Misslyckades att spara offert.");
      const data: SaveResponse = await res.json();
      setSavedId(data.id);
      setDraft(prev => prev || { title: data.title || "Sparad offert", subtotal_sek: data.subtotal_sek ?? 0, rot_discount_sek: data.rot_discount_sek ?? 0, total_sek: data.total_sek ?? 0, lines: [] });
    } catch(e:any){ setError(e.message || "Ett fel inträffade vid sparande."); }
    finally { setSavingQuote(false); }
  };

  const onFetch = async () => {
    setFetchError(null); setFetchedQuote(null);
    const id = fetchId.trim(); if(!id){ setFetchError("Ange ett offert-id."); return; }
    setFetching(true);
    try {
      const res = await fetch(`${API_BASE}/quotes/${encodeURIComponent(id)}`);
      if(!res.ok) throw new Error((await res.text()) || "Misslyckades att hämta offert.");
      const data = await res.json(); setFetchedQuote(data);
    } catch(e:any){ setFetchError(e.message || "Ett fel inträffade vid hämtning."); }
    finally { setFetching(false); }
  };

  const onPrint = () => window.print();

  const currentForPrint:any = fetchedQuote || (draft ? { ...draft, id: savedId } : null);
  const meta = currentForPrint ? { id: currentForPrint.id ?? savedId ?? "", date: new Date().toLocaleDateString("sv-SE") } : null;

  return (
    <div style={{ maxWidth: 920, margin: "0 auto", padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h1 className="no-print">Dockit AI – Offert</h1>

      <section className="no-print" style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={fetchHealth} disabled={loadingHealth}>{loadingHealth ? "Kontrollerar..." : "Kolla /health"}</button>
        <span>/health: {health}</span>
      </section>

      <section className="no-print" style={{ display: "grid", gap: 12, marginBottom: 24 }}>
        <div style={{ display: "grid", gap: 6 }}>
          <label htmlFor="customerName">Kundnamn</label>
          <input id="customerName" type="text" value={customerName} onChange={e=>setCustomerName(e.target.value)} placeholder="Dockit El & Data AB" />
        </div>
        <div style={{ display: "grid", gap: 6 }}>
          <label htmlFor="customerEmail">E-post</label>
          <input id="customerEmail" type="email" value={customerEmail} onChange={e=>setCustomerEmail(e.target.value)} placeholder="info@dockit.se" />
        </div>
        <div style={{ display: "grid", gap: 6 }}>
          <label htmlFor="jobSummary">Jobbbeskrivning</label>
          <textarea id="jobSummary" value={jobSummary} onChange={e=>setJobSummary(e.target.value)} placeholder="Installation av belysning och uttag i hall" rows={3} />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input id="applyRot" type="checkbox" checked={applyRot} onChange={e=>setApplyRot(e.target.checked)} />
          <label htmlFor="applyRot">Tillämpa ROT (30% av arbete)</label>
        </div>
      </section>

      <section className="no-print">
        <h2>Rader</h2>
        <div style={{ display: "grid", gap: 12 }}>
          {lines.map((line, idx) => (
            <div key={idx} style={{ display: "grid", gridTemplateColumns: "140px 1fr 120px 160px 90px", gap: 8, alignItems: "center" }}>
              <div style={{ display: "grid", gap: 4 }}>
                <label>Typ</label>
                <select value={line.kind} onChange={e=>updateLine(idx,{ kind: e.target.value as LineKind })}>
                  <option value="work">Arbete</option><option value="material">Material</option>
                </select>
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                <label>Beskrivning</label>
                <input type="text" value={line.description} onChange={e=>updateLine(idx,{ description: e.target.value })} placeholder={line.kind==="work" ? "Elmontör, installation..." : "LED-armatur infälld"} />
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                <label>Antal</label>
                <input type="number" min={0} step={1} value={line.qty} onChange={e=>updateLine(idx,{ qty: Number(e.target.value) })} />
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                <label>À-pris (SEK)</label>
                <input type="number" min={0} step="0.01" value={line.unit_price_sek} onChange={e=>updateLine(idx,{ unit_price_sek: Number(e.target.value) })} />
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                <label>&nbsp;</label>
                <button type="button" onClick={()=>removeLine(idx)} disabled={lines.length===1}>Ta bort</button>
              </div>
            </div>
          ))}
          <div><button type="button" onClick={addLine}>+ Lägg till rad</button></div>
        </div>
      </section>

      <section className="no-print" style={{ display: "flex", gap: 12, marginTop: 20, marginBottom: 12 }}>
        <button onClick={onDraft} disabled={submittingDraft}>{submittingDraft ? "Beräknar..." : "Beräkna offert (ROT)"}</button>
        <button onClick={onSave} disabled={savingQuote}>{savingQuote ? "Sparar..." : "Spara offert"}</button>
        <button onClick={onPrint} disabled={!draft && !fetchedQuote}>Exportera PDF</button>
      </section>

      {error && <div className="no-print" style={{ background: "#ffe6e6", border: "1px solid #ffb3b3", padding: 12, marginTop: 8 }}>{error}</div>}

      {(draft || savedId) && (
        <section className="no-print" style={{ marginTop: 20, borderTop: "1px solid #ddd", paddingTop: 16 }}>
          {draft && (
            <>
              <h3>{draft.title}</h3>
              <div style={{ display: "grid", gap: 4, maxWidth: 360 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span>Subtotal:</span><strong>{formatCurrency(draft.subtotal_sek)} SEK</strong></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span>ROT-avdrag:</span><strong>- {formatCurrency(draft.rot_discount_sek)} SEK</strong></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span>Totalt:</span><strong>{formatCurrency(draft.total_sek)} SEK</strong></div>
              </div>
            </>
          )}
          {savedId && <p style={{ marginTop: 12 }}>Offert sparad med id: <strong>{savedId}</strong></p>}
        </section>
      )}

      {currentForPrint && (
        <div ref={printRef} className="print-card">
          <div className="print-header">
            <div className="brand">
              <img className="logo" src="/dockit-logo.svg" alt="Dockit" />
            </div>
            <div className="meta">
              <div>Offertnr: <strong>{meta?.id ?? "-"}</strong></div>
              <div>Datum: <strong>{meta?.date}</strong></div>
            </div>
          </div>

          <div className="print-title">Offert</div>
          <div className="print-meta"><strong>Kund:</strong> {customerName}</div>
          <div className="print-meta"><strong>E-post:</strong> {customerEmail}</div>
          <div className="print-meta"><strong>Sammanfattning:</strong> {jobSummary}</div>

          <table className="print-table">
            <thead><tr><th>Typ</th><th>Beskrivning</th><th>Antal</th><th>À-pris (SEK)</th></tr></thead>
            <tbody>
              {(currentForPrint.lines || []).map((ln: any, i: number) => (
                <tr key={i}><td>{ln.kind}</td><td>{ln.description}</td><td>{ln.qty}</td><td>{formatCurrency(ln.unit_price_sek)} SEK</td></tr>
              ))}
            </tbody>
          </table>

          <div className="print-summary">
            <div className="print-summary-row"><span>Subtotal:</span><strong>{formatCurrency(currentForPrint.subtotal_sek)} SEK</strong></div>
            <div className="print-summary-row"><span>ROT-avdrag:</span><strong>- {formatCurrency(currentForPrint.rot_discount_sek)} SEK</strong></div>
            <div className="print-summary-row"><span>Totalt:</span><strong>{formatCurrency(currentForPrint.total_sek)} SEK</strong></div>
          </div>

          <div className="print-footer">Dockit – offert genererad från Dockit UI</div>
        </div>
      )}
    </div>
  );
}

function formatCurrency(value: number | undefined | null) {
  if (value == null) return "0";
  try { return new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 2 }).format(value); }
  catch { return String(value); }
}
