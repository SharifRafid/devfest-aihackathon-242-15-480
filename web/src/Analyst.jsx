import { useEffect, useState } from 'react'
import { api, FEATURE_LABEL, TIER, fmtBDT } from './api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from 'recharts'

const pct = v => (v == null ? '—' : (v * 100).toFixed(1) + '%')

export default function Analyst({ metrics, session, onSelectSession }) {
  const [alerts, setAlerts] = useState([]); const [accounts, setAccounts] = useState([]); const [narr, setNarr] = useState(null); const [busy, setBusy] = useState(false)
  useEffect(() => { api.alerts().then(setAlerts); api.accounts().then(setAccounts) }, [])
  useEffect(() => { setNarr(null) }, [session?.session_id])
  const pick = async a => { setBusy(true); try { onSelectSession(await api.replay(a.session_id)) } finally { setBusy(false) } }
  const explain = async () => {
    const last = session.steps[session.steps.length - 1]
    setNarr({ text: 'Writing…' })
    setNarr(await api.narrative({ session_id: session.session_id, user_id: session.user_id, score: session.final_score, n_events: session.n_events, top_reasons: last.reasons.map(r => FEATURE_LABEL[r.feature] || r.feature), features: session.features, decision: session.decision }))
  }
  const last = session?.steps?.[session.steps.length - 1]
  const ra = metrics?.recall_by_archetype || {}; const rb = metrics?.rule_baseline?.recall_by_archetype || {}; const ru = metrics?.unsupervised_only?.recall_by_archetype || {}
  const chart = Object.keys(ra).map(k => ({ name: k.split('_')[0], 'Second Thought': +(ra[k] * 100).toFixed(1), 'Rule baseline': +((rb[k] || 0) * 100).toFixed(1), 'Unsupervised only': +((ru[k] || 0) * 100).toFixed(1) }))
  const lat = metrics?.detection_latency; const op = metrics?.operating_point; const fair = metrics?.fairness_false_friction_by_slice
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div className="space-y-4">
        <div className="rounded-xl border border-white/10 bg-[#0f1520]">
          <div className="p-3 border-b border-white/10 font-semibold text-sm">Alert queue <span className="text-white/40 font-normal">held-out month, top by score</span></div>
          <div className="max-h-[340px] overflow-auto text-xs">
            {alerts.map(a => (
              <button key={a.session_id} onClick={() => pick(a)} className={`w-full text-left px-3 py-2 border-b border-white/5 hover:bg-white/5 flex items-center gap-2 ${session?.session_id === a.session_id ? 'bg-white/10' : ''}`}>
                <span className="mono text-red-300 w-10">{a.score.toFixed(2)}</span><span className="mono text-white/70 w-16">{a.user_id}</span><span className="text-white/50 flex-1 truncate">{a.persona}</span><span className="text-white/70">{fmtBDT(a.money_total)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-[#0f1520]">
          <div className="p-3 border-b border-white/10 font-semibold text-sm">Account-role misuse <span className="text-white/40 font-normal">personal wallet acting as merchant/agent (L4)</span></div>
          <table className="w-full text-xs"><thead className="text-white/40"><tr><th className="text-left p-2">user</th><th>p</th><th>inbound/30d</th><th>senders</th><th>cash-outs</th><th>round%</th></tr></thead>
            <tbody>{accounts.slice(0, 8).map(a => <tr key={a.user_id} className="border-t border-white/5"><td className="p-2 mono">{a.user_id}<span className="text-white/30"> {a.persona}</span></td><td className={`text-center mono ${a.p > .5 ? 'text-red-300' : 'text-white/50'}`}>{a.p.toFixed(2)}</td><td className="text-center">{a.inbound_tx_30d}</td><td className="text-center">{a.unique_senders_30d}</td><td className="text-center">{a.cashout_count_30d}</td><td className="text-center">{Math.round(a.round_amount_ratio * 100)}</td></tr>)}</tbody></table>
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-xl border border-white/10 bg-[#0f1520] p-3 space-y-3 min-h-[300px]">
          <div className="font-semibold text-sm">Case view {busy && <span className="text-white/40 font-normal">loading…</span>}</div>
          {!session && <div className="text-xs text-white/40">Pick an alert.</div>}
          {session && last && <>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="mono">{session.session_id}</span><span className="mono text-white/50">{session.user_id}</span>
              <span className={`px-2 py-0.5 rounded-full border ${TIER[session.decision.tier].color}`}>{TIER[session.decision.tier].label}</span>
              <span className="text-white/50">score {session.final_score.toFixed(3)} · {session.n_events} events · fired at {session.detect_at ?? '—'} · money call at {session.first_money_k ?? '—'}</span>
            </div>
            <div>
              <div className="text-xs text-white/50 mb-1">Why (SHAP, positive contributions)</div>
              {last.reasons.map(r => <div key={r.feature} className="flex items-center gap-2 text-xs mb-1"><span className="w-44 truncate text-white/80">{FEATURE_LABEL[r.feature] || r.feature}</span><div className="flex-1 h-2 bg-white/10 rounded"><div className="h-2 bg-red-400 rounded" style={{ width: `${Math.min(100, r.shap / (last.reasons[0].shap || 1) * 100)}%` }} /></div><span className="mono text-white/50 w-16 text-right">{r.value}</span></div>)}
            </div>
            <div className="text-xs text-white/70"><b>Policy:</b> {session.decision.rationale}</div>
            <div className="text-xs text-white/50">Profile at the time: {session.profile.n_prior_sessions} prior sessions · {session.profile.known_recipients} known recipients · usual hour {session.profile.usual_hour?.toFixed(1) ?? '—'}</div>
            <div className="flex flex-wrap gap-2">{session.decision.analyst_actions.map(a => <button key={a} className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/15 text-xs">{a.replace(/_/g, ' ')}</button>)}<button onClick={explain} className="px-2.5 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-xs">Write investigation summary</button></div>
            {narr && <div className="rounded-lg bg-white/5 p-3 text-xs text-white/80 whitespace-pre-wrap"><div className="text-white/40 mb-1">Generated text ({narr.source}{narr.model ? ' · ' + narr.model : ''}) — grounded only in the evidence JSON above; predictions and generated prose are kept separate.</div>{narr.text}</div>}
            {session.jev && <div className="text-[11px] text-white/40">Typed-decision layer (Jev): {session.jev.decided_by}{session.jev.tier ? ` → ${session.jev.tier}` : ''}</div>}
            {session.ground_truth && <div className="text-[11px] text-white/30">Ground truth (hidden from a real analyst): {session.ground_truth.archetype}</div>}
          </>}
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          {[['AUC', metrics?.auc], ['PR-AUC', metrics?.pr_auc], ['Recall @2% friction', pct(op?.recall)], ['Stopped before money moved', pct(lat?.stopped_at_or_before_first_money_request)],
            ['Median events to detect', lat?.median_events_to_detect], ['Money protected (test month)', lat ? fmtBDT(lat.money_protected_bdt) : '—']].map(([k, v]) => (
              <div key={k} className="rounded-lg border border-white/10 bg-[#0f1520] p-2.5"><div className="text-[11px] text-white/40">{k}</div><div className="text-lg font-semibold mono">{v ?? '—'}</div></div>))}
        </div>
        <div className="rounded-xl border border-white/10 bg-[#0f1520] p-3">
          <div className="text-xs text-white/60 mb-2">Recall by archetype at 2% false friction (%)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chart}><CartesianGrid stroke="#ffffff12" vertical={false} /><XAxis dataKey="name" tick={{ fill: '#9aa4b2', fontSize: 11 }} /><YAxis domain={[0, 100]} tick={{ fill: '#9aa4b2', fontSize: 11 }} /><Tooltip contentStyle={{ background: '#0f1520', border: '1px solid #ffffff22', fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Second Thought" fill="#34d399" /><Bar dataKey="Unsupervised only" fill="#60a5fa" /><Bar dataKey="Rule baseline" fill="#f87171" /></BarChart>
          </ResponsiveContainer>
          <div className="text-[11px] text-white/40 mt-1">Rule baseline false friction: {pct(metrics?.rule_baseline?.false_friction)} vs ours {pct(op?.false_friction)}. Rules miss the coerced victim (A3) almost entirely because the victim <i>is</i> the human.</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-[#0f1520] p-3 text-xs space-y-2">
          <div className="text-white/60">Novel-attack holdout (A5 removed from training)</div>
          <div className="flex gap-3"><span>supervised, never saw A5: <b className="mono">{pct(metrics?.novel_attack_holdout?.recall_supervised_never_saw_A5)}</b></span><span>unsupervised L1+L5: <b className="mono">{pct(metrics?.novel_attack_holdout?.recall_unsupervised_L1_L5)}</b></span></div>
          <div className="text-white/60 pt-1">False friction on genuine users by slice (fairness)</div>
          {fair && <div className="grid grid-cols-2 gap-x-4">{Object.entries(fair.persona).map(([k, v]) => <div key={k} className="flex justify-between"><span className="text-white/50">{k}</span><span className="mono">{pct(v)}</span></div>)}
            {Object.entries(fair.feature_phone).map(([k, v]) => <div key={k} className="flex justify-between"><span className="text-white/50">feature phone {k}</span><span className="mono">{pct(v)}</span></div>)}
            {Object.entries(fair.age_band || {}).map(([k, v]) => <div key={k} className="flex justify-between"><span className="text-white/50">age {k}</span><span className="mono">{pct(v)}</span></div>)}</div>}
        </div>
      </div>
    </div>
  )
}
