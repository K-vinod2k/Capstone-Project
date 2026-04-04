import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Bot,
  Send,
  MessageSquare,
  Activity,
  Video,
  Loader2,
  Settings,
  Globe,
  Zap,
  Sparkles,
  Film,
  Cpu,
} from 'lucide-react';

interface GenerationResult {
  spoken_reply: string;
  gesture_description: string;
  detected_persona: string;
  hero_icon: string;
  reference_video_b64: string;
  simulation_video_b64: string;
  error?: string;
}

const HERO_THEMES: Record<string, { badge: string; accent: string }> = {
  'Spider-Man': { badge: 'bg-red-500/10 border-red-500/40 text-red-300', accent: 'text-red-400' },
  'Iron Man': { badge: 'bg-yellow-500/10 border-yellow-500/40 text-yellow-300', accent: 'text-yellow-400' },
  'Hulk': { badge: 'bg-green-500/10 border-green-500/40 text-green-300', accent: 'text-green-400' },
  'Captain America': { badge: 'bg-blue-500/10 border-blue-500/40 text-blue-300', accent: 'text-blue-400' },
  'Thor': { badge: 'bg-purple-500/10 border-purple-500/40 text-purple-300', accent: 'text-purple-400' },
  'Black Widow': { badge: 'bg-slate-500/10 border-slate-500/40 text-slate-300', accent: 'text-slate-400' },
  'Batman': { badge: 'bg-gray-500/10 border-gray-500/40 text-gray-300', accent: 'text-gray-400' },
  'Superman': { badge: 'bg-blue-600/10 border-blue-600/40 text-blue-400', accent: 'text-blue-400' },
  'Generic Hero': { badge: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300', accent: 'text-emerald-400' },
};

function VideoPanel({
  title,
  badge,
  badgeColor,
  src,
  loading,
  loadingLabel,
  icon: Icon,
}: {
  title: string;
  badge?: string;
  badgeColor: string;
  src?: string;
  loading: boolean;
  loadingLabel: string;
  icon: React.ElementType;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] font-bold text-white/30 uppercase tracking-widest flex items-center gap-1.5">
          <Icon className="w-3 h-3" /> {title}
        </span>
        {src && (
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${badgeColor}`}>
            {badge}
          </span>
        )}
      </div>
      <div className="aspect-video bg-black border border-white/10 rounded-2xl overflow-hidden relative">
        {loading && (
          <div className="absolute inset-0 z-10 bg-black/70 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
            <p className="text-xs font-mono text-white/40 animate-pulse">{loadingLabel}</p>
          </div>
        )}
        {src ? (
          <motion.video
            key={src}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            src={src.startsWith('data:') ? src : `data:video/mp4;base64,${src}`}
            controls
            autoPlay
            loop
            muted
            className="w-full h-full object-cover"
          />
        ) : !loading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/10">
            <Icon className="w-10 h-10" />
            <p className="text-xs font-mono">Awaiting generation</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function App() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [ngrokUrl, setNgrokUrl] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  const theme = HERO_THEMES[result?.detected_persona ?? ''] ?? HERO_THEMES['Generic Hero'];

  const handleUpdateNgrok = async () => {
    if (!ngrokUrl.trim()) return;
    try {
      await fetch('http://localhost:8080/api/set_ngrok', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: ngrokUrl }),
      });
      alert('✅ Colab URL Updated!');
    } catch {
      alert('❌ Could not reach server at localhost:8080');
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('http://localhost:8080/api/run_pipeline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_prompt: prompt }),
      });
      if (!res.ok) throw new Error('Pipeline failed');
      setResult(await res.json());
    } catch (e) {
      setResult({
        spoken_reply: '', gesture_description: '',
        detected_persona: '', hero_icon: '',
        reference_video_b64: '', simulation_video_b64: '',
        error: 'Backend failed. Is the server running at localhost:8080?',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08080f] text-white font-sans">

      {/* Header */}
      <header className="border-b border-white/5 bg-black/60 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center shadow-lg shadow-emerald-500/30">
              <Bot className="w-5 h-5 text-black" />
            </div>
            <div>
              <h1 className="text-sm font-bold">Mascot Unitree</h1>
              <p className="text-[10px] text-white/30 font-mono uppercase tracking-widest">Hero Activation System</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-white/30">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            System Active
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* ── LEFT PANEL ── */}
          <aside className="lg:col-span-3 space-y-4">

            {/* Hero Badge */}
            <AnimatePresence>
              {result?.detected_persona && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`border rounded-2xl p-4 flex items-center gap-3 ${theme.badge}`}
                >
                  <span className="text-3xl">{result.hero_icon}</span>
                  <div>
                    <p className="text-[9px] uppercase tracking-widest opacity-50">Hero Detected</p>
                    <p className="font-bold">{result.detected_persona}</p>
                  </div>
                  <Zap className="w-3.5 h-3.5 ml-auto animate-pulse" />
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
              <label className="text-[10px] font-bold text-white/40 uppercase tracking-widest flex items-center gap-1.5">
                <MessageSquare className="w-3 h-3" /> Call Your Hero
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && e.metaKey) handleGenerate(); }}
                placeholder={"Try:\n\"Hey Spider-Man, save me!\"\n\"Iron Man we need you!\"\n\"HULK SMASH this!\""}
                className="w-full h-32 bg-black/40 border border-white/10 rounded-xl p-3 text-sm focus:outline-none focus:border-emerald-500/40 resize-none placeholder:text-white/15 leading-relaxed"
              />
              <button
                onClick={handleGenerate}
                disabled={loading || !prompt.trim()}
                className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed text-black font-bold py-3 rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98] shadow-lg shadow-emerald-500/20 text-sm"
              >
                {loading
                  ? <><Loader2 className="w-4 h-4 animate-spin" /><span>Activating...</span></>
                  : <><Send className="w-4 h-4" /><span>Activate Hero</span></>}
              </button>
            </div>

            {/* Colab Settings */}
            <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <button
                onClick={() => setShowSettings(!showSettings)}
                className="w-full p-4 flex items-center justify-between text-white/40 hover:text-white/60 text-xs transition-colors"
              >
                <span className="flex items-center gap-2 font-semibold uppercase tracking-wider">
                  <Settings className="w-3 h-3" /> Advanced (Colab Fallback)
                </span>
                <span>{showSettings ? '▲' : '▼'}</span>
              </button>
              <AnimatePresence>
                {showSettings && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="px-5 pb-5 space-y-3"
                  >
                    <p className="text-[10px] text-white/30 uppercase tracking-widest flex items-center gap-1">
                      <Globe className="w-2.5 h-2.5" /> Colab Ngrok URL (Optional)
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={ngrokUrl}
                        onChange={(e) => setNgrokUrl(e.target.value)}
                        placeholder="https://xxxx.ngrok-free.app"
                        className="flex-1 bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono focus:border-emerald-500/40 focus:outline-none"
                      />
                      <button
                        onClick={handleUpdateNgrok}
                        className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-3 py-2 rounded-lg text-xs font-bold hover:bg-emerald-500/20 transition-colors"
                      >Set</button>
                    </div>
                    <p className="text-[10px] text-white/20">Paste Colab ngrok URL then click Set.</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Status */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-2">
              <p className="text-[10px] font-bold text-white/30 uppercase tracking-widest flex items-center gap-1.5 mb-3">
                <Activity className="w-3 h-3" /> Pipeline Status
              </p>
              <StatusRow label="Persona Engine" ok={true} />
              <StatusRow label="Veo 3.1" ok={true} note="Google cloud" />
              <StatusRow label="MuJoCo Sim" ok={true} />
            </div>
          </aside>

          {/* ── RIGHT PANEL ── */}
          <div className="lg:col-span-9 space-y-6">

            {/* LLM Output Cards */}
            <section className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 border border-white/10 rounded-2xl p-5 min-h-[110px]">
                <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                  <Sparkles className="w-3 h-3" /> Signature Dialogue
                </p>
                <div className="text-white/85 text-lg font-medium italic leading-snug">
                  {loading
                    ? <span className="text-sm not-italic text-white/30 animate-pulse">LLM thinking...</span>
                    : result?.spoken_reply
                      ? <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}>"{result.spoken_reply}"</motion.span>
                      : <span className="text-sm not-italic text-white/20">Awaiting hero call...</span>}
                </div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-2xl p-5 min-h-[110px]">
                <p className="text-[10px] font-bold text-blue-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                  <Cpu className="w-3 h-3" /> Video Prompt (Gesture)
                </p>
                <p className="text-white/50 text-sm leading-relaxed">
                  {loading
                    ? <span className="animate-pulse">Generating gesture description...</span>
                    : result?.gesture_description || 'No gesture yet.'}
                </p>
              </div>
            </section>

            {/* Dual Video Section */}
            <section className="space-y-3">
              <h2 className="text-[10px] font-bold text-white/30 uppercase tracking-widest flex items-center gap-2">
                <Film className="w-3 h-3" /> Video Outputs
              </h2>
              <div className="grid grid-cols-2 gap-5">
                <VideoPanel
                  title="AI Generated (Veo 3.1)"
                  badge="VEO 3.1 · AI"
                  badgeColor="bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                  src={result?.reference_video_b64}
                  loading={loading}
                  loadingLabel="Veo 3.1 generating video (~1-2 min)..."
                  icon={Video}
                />
                <VideoPanel
                  title="MuJoCo Simulation"
                  badge="MUJOCO · SIM"
                  badgeColor="bg-blue-500/15 border-blue-500/30 text-blue-400"
                  src={result?.simulation_video_b64}
                  loading={loading}
                  loadingLabel="Rendering physics sim..."
                  icon={Activity}
                />
              </div>
            </section>

            {/* Error */}
            <AnimatePresence>
              {result?.error && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm flex items-start gap-3"
                >
                  <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse mt-1 shrink-0" />
                  {result.error}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatusRow({ label, ok, note }: { label: string; ok: boolean; note?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-white/50">{label}</span>
      <span className={`flex items-center gap-1.5 ${ok ? 'text-emerald-400' : 'text-yellow-500'}`}>
        <div className={`w-1 h-1 rounded-full ${ok ? 'bg-emerald-400' : 'bg-yellow-500'}`} />
        {note ?? (ok ? 'Online' : 'Standby')}
      </span>
    </div>
  );
}
