import { useState } from 'react'
import { fmtBDT, TIER } from './api'
import { ShieldCheck, PhoneCall, AlertTriangle, Lock } from 'lucide-react'

export default function Phone({ session }) {
  const [lang, setLang] = useState('bn')
  const [state, setState] = useState('screen') // screen | confirmed | cancelled | reported | cooling
  const d = session?.decision
  const tier = d?.tier || 'allow'
  const money = session?.steps?.find(s => s.amount > 0)
  const bn = lang === 'bn'
  const reasons = bn ? d?.reasons_bn : d?.reasons_en
  const msg = bn ? d?.message_bn : d?.message_en
  const t = v => (bn ? v[1] : v[0])

  const Body = () => {
    if (!session) return <div className="p-6 text-center text-black/50 text-sm">Finish a replay or pick an alert to see what the customer sees.</div>
    if (tier === 'allow') return (
      <div className="p-6 text-center space-y-3">
        <ShieldCheck className="mx-auto text-emerald-600" size={48} />
        <div className="font-semibold text-black">{t(['Sent successfully', 'সফলভাবে পাঠানো হয়েছে'])}</div>
        {money && <div className="text-2xl font-bold text-black">{fmtBDT(money.amount)}</div>}
        <div className="text-xs text-black/50">{t(['No friction: this session looked like you.', 'কোনো বাধা নেই: এই সেশনটি আপনার মতোই দেখাচ্ছিল।'])}</div>
      </div>
    )
    if (state === 'reported' || tier === 'hold') return (
      <div className="p-6 text-center space-y-3">
        <Lock className="mx-auto text-red-600" size={48} />
        <div className="font-semibold text-black">{t(['Transaction paused', 'লেনদেন স্থগিত'])}</div>
        <div className="text-sm text-black/70">{bn ? d.message_bn || 'নিরাপত্তা পর্যালোচনার জন্য এই লেনদেনটি স্থগিত করা হয়েছে। আমাদের দল আপনার সাথে যোগাযোগ করবে।' : d.message_en || 'This transaction has been paused for a security review. Our team will contact you.'}</div>
        <div className="text-xs text-black/50">{t(['A human analyst decides. Nothing is blocked permanently by the model.', 'একজন মানুষ বিশ্লেষক সিদ্ধান্ত নেবেন। মডেল কিছুই স্থায়ীভাবে ব্লক করে না।'])}</div>
      </div>
    )
    if (state === 'cancelled') return (
      <div className="p-6 text-center space-y-3">
        <ShieldCheck className="mx-auto text-emerald-600" size={48} />
        <div className="font-semibold text-black">{t(['Cancelled. Your money stays with you.', 'বাতিল হয়েছে। আপনার টাকা আপনার কাছেই আছে।'])}</div>
        <div className="text-xs text-black/50">{t(['If someone pressured you, call 16268 (upay helpline).', 'কেউ চাপ দিলে ১৬২৬৮ (উপায় হেল্পলাইন) এ কল করুন।'])}</div>
      </div>
    )
    if (state === 'confirmed') return (
      <div className="p-6 text-center space-y-3">
        {tier === 'step_up' ? <PhoneCall className="mx-auto text-orange-600" size={48} /> : <ShieldCheck className="mx-auto text-emerald-600" size={48} />}
        <div className="font-semibold text-black">{tier === 'step_up' ? t(['We will call you to verify', 'যাচাইয়ের জন্য আমরা আপনাকে কল করব']) : t(['Sent after confirmation', 'নিশ্চিত করার পর পাঠানো হয়েছে'])}</div>
        <div className="text-xs text-black/50">{tier === 'step_up' ? t(['The transfer executes only after verification.', 'যাচাইয়ের পরেই লেনদেন সম্পন্ন হবে।']) : t(['You stayed in control.', 'আপনিই নিয়ন্ত্রণে ছিলেন।'])}</div>
      </div>
    )
    return (
      <div className="p-5 space-y-4">
        <div className="flex items-center gap-2 text-amber-700"><AlertTriangle size={20} /><span className="font-semibold">{t(['Second Thought', 'একটু ভাবুন'])}</span></div>
        {money && <div className="rounded-lg bg-black/5 p-3 text-black">
          <div className="text-xs text-black/50">{t(['You are about to send', 'আপনি পাঠাতে যাচ্ছেন'])}</div>
          <div className="text-2xl font-bold">{fmtBDT(money.amount)}</div>
          <div className="text-xs text-black/50 mono">{t(['to', 'প্রাপক'])} {money.recipient || '—'}</div>
        </div>}
        <ul className="space-y-1.5 text-sm text-black/80">{(reasons || []).map((r, i) => <li key={i} className="flex gap-2"><span className="text-amber-600">•</span>{r}</li>)}</ul>
        <div className="text-sm text-black font-medium">{msg}</div>
        <div className="space-y-2 pt-1">
          <button onClick={() => setState('cancelled')} className="w-full py-2.5 rounded-lg bg-emerald-600 text-white font-medium">{t(['Cancel, I am not sure', 'বাতিল করুন, আমি নিশ্চিত নই'])}</button>
          <button onClick={() => setState('reported')} className="w-full py-2.5 rounded-lg bg-white border border-red-300 text-red-700 font-medium">{t(['Someone on the phone asked me to', 'ফোনে কেউ আমাকে করতে বলেছে'])}</button>
          <button onClick={() => setState('confirmed')} className="w-full py-2 rounded-lg text-black/50 text-sm">{t([tier === 'step_up' ? 'Yes, verify me and continue' : 'Yes, I know this person. Continue', tier === 'step_up' ? 'হ্যাঁ, যাচাই করুন এবং এগিয়ে যান' : 'হ্যাঁ, আমি একে চিনি। এগিয়ে যান'])}</button>
        </div>
        {d?.cooling_seconds ? <div className="text-[11px] text-black/40 text-center">{t([`${d.cooling_seconds}s cooling period before "Continue" activates`, `"এগিয়ে যান" সক্রিয় হওয়ার আগে ${d.cooling_seconds} সেকেন্ড অপেক্ষা`])}</div> : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6 items-start">
      <div className="mx-auto w-[340px] rounded-[2.2rem] border-[10px] border-black bg-white text-black shadow-2xl overflow-hidden">
        <div className="bg-[#e4007c] text-white px-4 py-3 flex items-center justify-between">
          <div className="font-bold tracking-wide">upay</div>
          <button onClick={() => setLang(bn ? 'en' : 'bn')} className="text-xs bg-white/20 rounded px-2 py-0.5">{bn ? 'EN' : 'বাং'}</button>
        </div>
        <div className="min-h-[520px]"><Body /></div>
      </div>
      <div className="flex-1 space-y-3 text-sm">
        <h3 className="font-semibold">What the customer sees, and why</h3>
        <p className="text-white/60">The model never talks to the customer directly. The policy layer picks a tier, and the top SHAP drivers are translated into plain Bangla or English sentences. The LLM is not involved in this screen at all, so nothing here can hallucinate.</p>
        {session && <div className="rounded-lg border border-white/10 p-3 space-y-2">
          <div className="flex items-center gap-2"><span className={`text-xs px-2 py-0.5 rounded-full border ${TIER[tier].color}`}>{TIER[tier].label}</span><span className="text-xs text-white/50">score {session.final_score?.toFixed(3)} · human-likeness {d.human_likeness} {d.coercion_like && '· coercion pattern'}</span></div>
          <div className="text-white/70 text-xs">{d.rationale}</div>
          {session.ground_truth && <div className="text-xs text-white/40">Ground truth: {session.ground_truth.archetype}</div>}
        </div>}
        <div className="rounded-lg border border-white/10 p-3 text-xs text-white/60 space-y-1">
          <div><b className="text-white/80">Second Thought</b>: genuine person, scam-like situation. Explain, add a 30 s cooling period, offer an exit. Never block.</div>
          <div><b className="text-white/80">Step-up</b>: likely not the owner. Re-verify before the money call executes.</div>
          <div><b className="text-white/80">Hold</b>: traffic is not the genuine app. Pause and queue for a human analyst.</div>
        </div>
        <button onClick={() => setState('screen')} className="text-xs text-white/50 underline">reset phone</button>
      </div>
    </div>
  )
}
