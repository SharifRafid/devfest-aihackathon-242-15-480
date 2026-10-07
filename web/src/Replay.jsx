import { useEffect, useRef, useState } from 'react'
import { api, EVENT_LABEL, FEATURE_LABEL, TIER, fmtBDT } from './api'
import { Play, RotateCcw, Zap, ShieldAlert, Smartphone, Server } from 'lucide-react'

const MONEY = new Set(['a_transfer', 'a_cashout', 'a_recharge', 'a_billpay', 'a_merchantpay'])

function Lane({ title, data, cursor, onFinished }) {
  const steps = data?.steps || []
  const shown = steps.slice(0, cursor)
  const cur = shown[shown.length - 1]
  const fired = shown.find(s => s.tier !== 'allow')
  const listRef = useRef(null)
  useEffect(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight }, [cursor])
  const done = data && cursor >= steps.length
  useEffect(() => { if (done) onFinished?.() }, [done])
  const score = cur?.score ?? 0
  const t = TIER[cur?.tier || 'allow']
  return (
    <div className={`flex flex-col rounded-xl border bg-[#0f1520] ${fired ? 'border-red-500/50' : 'border-white/10'} min-h-[520px]`}>
      <div className="p-3 border-b border-white/10 flex items-center justify-between gap-2">
        <div className="font-semibold text-sm truncate">{title}</div>
        {data && <div className="text-xs text-white/50 mono">{data.user_id} · {data.persona}</div>}
      </div>
      <div className="px-3 pt-3">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-white/60">Session risk score</span>
          <span className={`mono font-semibold ${score >= data?.threshold ? 'text-red-300' : 'text-emerald-300'}`}>{score.toFixed(3)}</span>
        </div>
        <div className="h-3 rounded bg-white/10 overflow-hidden relative">
          <div className={`h-full transition-all duration-300 ${score >= (data?.threshold ?? 1) ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ width: `${Math.max(2, Math.min(100, score * 100))}%` }} />
          {data && <div className="absolute top-0 bottom-0 w-px bg-amber-300" style={{ left: `${data.threshold * 100}%` }} title="2% false-friction threshold" />}
        </div>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <span className={`text-[11px] px-2 py-0.5 rounded-full border ${t.color}`}>{t.label}</span>
          {cur && <span className="text-[11px] text-white/50">human-likeness {cur.human_likeness}</span>}
          {fired && <span className="text-[11px] text-red-300 flex items-center gap-1"><ShieldAlert size={12} /> fired at event {fired.k}{data.first_money_k ? ` · money call at ${data.first_money_k}` : ''}</span>}
        </div>
      </div>
      <div ref={listRef} className="flex-1 overflow-auto px-3 py-2 space-y-1 mono text-[11.5px] max-h-[300px]">
        {shown.map(s => {
          const isMoney = MONEY.has(s.event); const isScreen = s.event.startsWith('s_')
          const blocked = isMoney && s.tier !== 'allow'
          return (
            <div key={s.k} className={`flex items-center gap-2 rounded px-2 py-1 ${blocked ? 'bg-red-500/15 alarm' : s.tier !== 'allow' ? 'bg-amber-500/10' : 'bg-white/[0.03]'}`}>
              <span className="text-white/30 w-5 text-right">{s.k}</span>
              {isScreen ? <Smartphone size={12} className="text-sky-300" /> : <Server size={12} className={isMoney ? 'text-red-300' : 'text-white/40'} />}
              <span className={`flex-1 truncate ${isMoney ? 'text-red-200 font-semibold' : isScreen ? 'text-sky-100' : 'text-white/70'}`}>{EVENT_LABEL[s.event] || s.event}{s.amount ? ` ${fmtBDT(s.amount)}` : ''}{s.pin_error ? ' ✗PIN' : ''}</span>
              <span className="text-white/40 w-14 text-right">+{s.dt_ms >= 1000 ? (s.dt_ms / 1000).toFixed(1) + 's' : s.dt_ms + 'ms'}</span>
              <span className={`w-10 text-right ${s.score >= data.threshold ? 'text-red-300' : 'text-white/40'}`}>{s.score.toFixed(2)}</span>
            </div>
          )
        })}
      </div>
      {done && (
        <div className="p-3 border-t border-white/10 text-xs space-y-2">
          <div className="flex flex-wrap gap-1">
            {(data.steps[data.steps.length - 1].reasons || []).slice(0, 4).map(r => (
              <span key={r.feature} className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white/80">{FEATURE_LABEL[r.feature] || r.feature}</span>
            ))}
          </div>
          <div className="text-white/60">{data.decision.rationale}</div>
          {data.ground_truth && <div className="text-white/40">Ground truth: <span className={data.ground_truth.label === 'fraud' ? 'text-red-300' : 'text-emerald-300'}>{data.ground_truth.archetype}</span>
            {data.ground_truth.label === 'fraud' && <span> · {data.stopped_before_money ? 'stopped before money moved' : 'detected after first money call'}</span>}</div>}
        </div>
      )}
    </div>
  )
}

export default function Replay({ demo, onSelectSession }) {
  const [lanes, setLanes] = useState([null, null, null])
  const [cursors, setCursors] = useState([0, 0, 0])
  const [playing, setPlaying] = useState(false)
  const [picks, setPicks] = useState([])
  const timers = useRef([])

  useEffect(() => {
    if (!demo?.length) return
    const want = ['Genuine user', 'Scripted ATO via reverse-engineered API', 'Coerced victim on a scam call']
    const chosen = want.map(w => demo.find(d => d.label === w)).filter(Boolean)
    setPicks(chosen.map(c => c.session_id))
  }, [demo])

  useEffect(() => {
    if (!picks.length) return
    let alive = true
    Promise.all(picks.map(sid => api.replay(sid))).then(ds => { if (alive) { setLanes(ds); setCursors(ds.map(() => 0)) } })
    return () => { alive = false }
  }, [picks])

  const stop = () => { timers.current.forEach(clearTimeout); timers.current = []; setPlaying(false) }
  const play = () => {
    stop(); setPlaying(true); setCursors(lanes.map(() => 0))
    lanes.forEach((d, li) => {
      if (!d) return
      let k = 0
      const tick = () => {
        k += 1; setCursors(c => { const n = [...c]; n[li] = k; return n })
        if (k < d.steps.length) { const dt = d.steps[k].dt_ms; timers.current.push(setTimeout(tick, Math.min(1400, Math.max(120, dt / 3)))) }
      }
      timers.current.push(setTimeout(tick, 300))
    })
  }
  const reset = () => { stop(); setCursors(lanes.map(() => 0)) }
  const attack = async kind => {
    stop(); const d = await api.attack(kind)
    setLanes(l => { const n = [...l]; n[2] = d; return n }); setCursors(c => { const n = [...c]; n[2] = 0; return n })
    setTimeout(play, 100)
  }
  const titles = ['Genuine user', 'Scripted ATO (reverse-engineered API)', 'Coerced victim on a scam call']

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={play} disabled={playing || !lanes[0]} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-sm font-medium"><Play size={14} /> Play all three</button>
        <button onClick={reset} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-sm"><RotateCcw size={14} /> Reset</button>
        <div className="w-px h-6 bg-white/10 mx-1" />
        <span className="text-xs text-white/50">Attack me, live:</span>
        {[['A1', 'Scripted API'], ['A7', 'Adaptive (human-like timing)'], ['A2', 'OTP-relay takeover'], ['A3', 'Scam-call victim'], ['A6', 'Emulator farm'], ['A5', 'Gambling chain']].map(([k, l]) => (
          <button key={k} onClick={() => attack(k)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-red-600/80 hover:bg-red-500 text-xs"><Zap size={12} /> {l}</button>
        ))}
        <select className="ml-auto bg-white/5 border border-white/10 rounded-lg text-xs px-2 py-1.5" value="" onChange={e => { if (!e.target.value) return; const [li, sid] = e.target.value.split('|'); api.replay(sid).then(d => { setLanes(l => { const n = [...l]; n[+li] = d; return n }); setCursors(c => { const n = [...c]; n[+li] = 0; return n }) }) }}>
          <option value="">Load a demo session into a lane…</option>
          {[0, 1, 2].map(li => demo?.map(d => <option key={li + d.session_id} value={`${li}|${d.session_id}`}>Lane {li + 1} ← {d.label}</option>))}
        </select>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {lanes.map((d, i) => <Lane key={i} title={d?.simulated ? `LIVE: ${d.ground_truth.archetype}` : (d?.ground_truth ? titles[i] : 'Loading…')} data={d} cursor={cursors[i]} onFinished={() => onSelectSession?.(d)} />)}
      </div>
      <p className="text-xs text-white/40">Each lane is scored event by event by the same feature engine used in training, on the prefix available at that moment. Screens are <span className="text-sky-300">blue</span>, API calls grey, money-moving calls <span className="text-red-300">red</span>. The amber tick on the bar is the 2% false-friction threshold.</p>
    </div>
  )
}
