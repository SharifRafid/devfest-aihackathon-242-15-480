import { useEffect, useState } from 'react'
import { api } from './api'
import Replay from './Replay'
import Phone from './Phone'
import Analyst from './Analyst'
import { Activity, Smartphone, LayoutDashboard, ShieldCheck } from 'lucide-react'

const TABS = [['replay', 'Replay Theatre', Activity], ['phone', 'Customer screen', Smartphone], ['analyst', 'Analyst console', LayoutDashboard]]

export default function App() {
  const [tab, setTab] = useState('replay')
  const [demo, setDemo] = useState([]); const [metrics, setMetrics] = useState(null); const [health, setHealth] = useState(null); const [err, setErr] = useState(null)
  const [session, setSession] = useState(null)
  useEffect(() => { api.health().then(setHealth).catch(e => setErr(String(e))); api.demo().then(setDemo).catch(e => setErr(String(e))); api.metrics().then(setMetrics).catch(() => {}) }, [])
  const lat = metrics?.detection_latency
  return (
    <div className="min-h-screen">
      <header className="border-b border-white/10 bg-[#0d1219]">
        <div className="max-w-[1500px] mx-auto px-4 py-3 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2"><ShieldCheck className="text-[#e4007c]" /><div><div className="font-bold leading-tight">Second Thought</div><div className="text-[11px] text-white/50 leading-tight">Session-authenticity engine for MFS · scores the path to the transaction, not just the transaction</div></div></div>
          <nav className="flex gap-1 ml-auto">
            {TABS.map(([k, l, I]) => <button key={k} onClick={() => setTab(k)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm ${tab === k ? 'bg-white/15' : 'hover:bg-white/5 text-white/70'}`}><I size={14} /> {l}</button>)}
          </nav>
          {metrics && <div className="hidden md:flex gap-4 text-[11px] text-white/50 mono">
            <span>AUC {metrics.auc}</span><span>recall {(metrics.operating_point.recall * 100).toFixed(0)}% @ {(metrics.operating_point.false_friction * 100).toFixed(1)}% friction</span><span>stopped before money {(lat.stopped_at_or_before_first_money_request * 100).toFixed(0)}%</span><span className={health?.ok ? 'text-emerald-300' : 'text-red-300'}>{health?.static ? 'snapshot mode (no backend)' : health?.ok ? 'API live' : 'API down'}</span>
          </div>}
        </div>
      </header>
      <main className="max-w-[1500px] mx-auto px-4 py-4">
        {err && <div className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm">API not reachable: {err}. Start it with <code className="mono">make api</code>.</div>}
        {tab === 'replay' && <Replay demo={demo} onSelectSession={s => { if (s?.decision?.tier !== 'allow' || !session) setSession(s) }} />}
        {tab === 'phone' && <Phone session={session} />}
        {tab === 'analyst' && <Analyst metrics={metrics} session={session} onSelectSession={setSession} />}
      </main>
    </div>
  )
}
