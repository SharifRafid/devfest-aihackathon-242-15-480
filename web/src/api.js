// Live mode talks to the FastAPI scorer. If it is unreachable (static hosting), fall back to the
// snapshot exported by scripts/export_static.py — identical payloads, no backend required.
const BASE = import.meta.env.VITE_API || '/api'
let mode = import.meta.env.VITE_STATIC === '1' ? 'static' : 'unknown'
const cache = {}
async function st(name) { if (!cache[name]) cache[name] = fetch(`/static/${name}.json`).then(r => { if (!r.ok) throw new Error('static missing'); return r.json() }); return cache[name] }
async function live(url, opts) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500)
  try { const r = await fetch(BASE + url, { ...opts, signal: ctl.signal }); if (!r.ok) throw new Error(await r.text()); const data = await r.json(); mode = 'live'; return data }
  finally { clearTimeout(t) }
}
async function j(url, opts, fallback) {
  if (mode !== 'static') { try { return await live(url, opts) } catch (e) { if (mode === 'live') throw e; mode = 'static' } }
  return fallback()
}
export const getMode = () => mode
const rnd = a => a[Math.floor(Math.random() * a.length)]
export const api = {
  health: () => j('/health', undefined, () => st('health')),
  metrics: () => j('/metrics', undefined, () => st('metrics')),
  demo: () => j('/demo/sessions', undefined, () => st('demo_sessions')),
  replay: sid => j(`/sessions/${sid}/replay`, undefined, async () => { const r = (await st('replays'))[sid]; if (!r) throw new Error('not in snapshot'); return r }),
  attack: kind => j(`/simulate/attack?kind=${kind}`, { method: 'POST' }, async () => rnd((await st('attacks'))[kind])),
  alerts: () => j('/alerts', undefined, () => st('alerts')),
  accounts: () => j('/accounts/flagged', undefined, () => st('accounts_flagged')),
  narrative: body => j('/narrative', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) },
    async () => (await st('narratives'))[body.session_id] || { source: 'template', text: 'No snapshot narrative for a live-simulated session. Start the API for LLM narratives.' }),
}
export const EVENT_LABEL = {
  s_splash: 'Splash screen', s_login: 'Login screen', s_otp: 'OTP screen', s_home: 'Home screen', s_balance: 'Balance screen', s_send: 'Send Money screen',
  s_recipient: 'Recipient entry', s_amount: 'Amount entry', s_pin: 'PIN entry', s_confirm: 'Confirm screen', s_success: 'Success screen', s_cashout: 'Cash Out screen',
  s_recharge: 'Recharge screen', s_bill: 'Bill Pay screen', s_qr: 'QR Pay screen', s_addmoney: 'Add Money screen', s_statement: 'Statement screen', s_profile: 'Profile screen',
  s_help: 'Help screen', s_pinchange: 'PIN change screen', s_beneficiary: 'Add beneficiary screen',
  a_login: 'POST /auth/login', a_otp: 'POST /auth/otp', a_balance: 'GET /wallet/balance', a_offers: 'GET /offers (prefetch)', a_ping: 'POST /telemetry/ping',
  a_heartbeat: 'POST /telemetry/heartbeat', a_resolve_recipient: 'GET /recipient/resolve', a_transfer: 'POST /transfer', a_cashout: 'POST /cashout', a_recharge: 'POST /recharge',
  a_billpay: 'POST /billpay', a_merchantpay: 'POST /merchant/pay', a_addmoney: 'POST /addmoney', a_statement: 'GET /statement', a_pinchange: 'POST /pin/change',
  a_add_beneficiary: 'POST /beneficiary', a_logout: 'POST /auth/logout',
}
export const FEATURE_LABEL = {
  frac_new_recipient: 'first-ever recipient', new_recipient_count: 'new recipients', recipient_known_ratio: 'recipient not in history', money_max: 'amount vs history',
  money_total: 'total amount', amount_frac_cap: 'share of daily cap', amount_z: 'amount z-score vs user', is_night: 'night-time', hour_dev: 'hours from usual time',
  hesitation_ratio: 'hesitation vs usual', pin_errors: 'PIN errors', new_device: 'new device', has_pinchange: 'PIN changed', has_add_beneficiary: 'beneficiary added',
  mk_mean_nll: 'flow unlikely (Markov)', mk_min_logp: 'rare transition', mk_n_unseen: 'never-seen transitions', no_telemetry: 'telemetry missing', telemetry_ratio: 'telemetry ratio',
  screen_ratio: 'screens vs API calls', api_only_prefix: 'API calls only, no screens', money_without_pin_screen: 'transfer without PIN screen', dt_cv: 'timing uniformity',
  frac_dt_lt_300: 'sub-300ms gaps', dt_min: 'fastest gap', ms_per_char_min: 'typing speed', impossible_typing: 'impossible typing', money_per_minute: 'transfer velocity',
  device_user_count: 'accounts on this device', rhythm_ratio: 'pace vs usual', duration_s: 'session duration', n_prior_sessions: 'history length', has_help: 'visited Help',
  has_balance_check: 'checked balance', n_money: 'money calls', n_events: 'events', n_api: 'API calls', n_screens: 'screens', dt_mean: 'mean gap', dt_std: 'gap std', dt_median: 'median gap',
  frac_dt_lt_1000: 'sub-1s gaps', ms_per_char_mean: 'mean typing speed', telemetry_count: 'telemetry calls', has_otp: 'OTP step', login_without_screen: 'login without screen', hour: 'hour of day',
}
export const TIER = {
  allow: { label: 'Allow', color: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  second_thought: { label: 'Second Thought', color: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  step_up: { label: 'Step-up verify', color: 'bg-orange-500/15 text-orange-300 border-orange-500/40' },
  hold: { label: 'Hold + analyst', color: 'bg-red-500/15 text-red-300 border-red-500/40' },
}
export const fmtBDT = n => '৳' + Math.round(n).toLocaleString('en-IN')
