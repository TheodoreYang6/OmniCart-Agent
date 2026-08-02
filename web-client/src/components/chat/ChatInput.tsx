import { useRef, useState, type KeyboardEvent } from 'react'
import { ArrowUp, BrainCircuit, ImagePlus, Mic, Square, X, Zap } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder'
import { toast } from '@/store/toastStore'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  // IME 组合态保护：中文输入法按 Enter 确认候选词时不能当成发送
  const composingRef = useRef(false)
  const compositionEndedAtRef = useRef(0)

  const fastMode = useChatStore((s) => s.fastMode)
  const setFastMode = useChatStore((s) => s.setFastMode)
  const deepThink = useChatStore((s) => s.deepThink)
  const setDeepThink = useChatStore((s) => s.setDeepThink)
  const pendingPreview = useChatStore((s) => s.pendingImagePreview)
  const setPendingImage = useChatStore((s) => s.setPendingImage)
  const transcribe = useChatStore((s) => s.transcribe)

  const recorder = useVoiceRecorder()
  const [transcribing, setTranscribing] = useState(false)

  const canSend = (text.trim().length > 0 || !!pendingPreview) && !disabled

  const handleSend = () => {
    if (!canSend) return
    onSend(text)
    setText('')
    if (taRef.current) taRef.current.style.height = 'auto'
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      // 组合态中的 Enter 是确认候选词；Safari 会先发 compositionend 再发 keydown
      //（此时 isComposing 已为 false），故再用时间戳兜底判定
      if (
        composingRef.current ||
        e.nativeEvent.isComposing ||
        Date.now() - compositionEndedAtRef.current < 100
      ) {
        return
      }
      e.preventDefault()
      handleSend()
    }
  }

  const autoGrow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`
  }

  const onPickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (!file.type.startsWith('image/')) {
        toast.error('请选择图片文件')
        return
      }
      setPendingImage(file)
    }
    e.target.value = ''
  }

  const startVoice = async () => {
    if (!recorder.supported) {
      toast.error('当前浏览器不支持录音')
      return
    }
    const ok = await recorder.start()
    if (!ok) toast.error('无法访问麦克风，请检查权限')
  }

  const stopVoice = async () => {
    const result = await recorder.stop()
    if (!result) return
    setTranscribing(true)
    try {
      const asrText = await transcribe(result.blob, result.filename)
      if (asrText) {
        onSend(asrText)
      } else {
        toast.error('没有识别到语音内容')
      }
    } finally {
      setTranscribing(false)
    }
  }

  return (
    <div className="px-3 pb-3 pt-1 sm:px-4">
      <div className="glass-strong mx-auto max-w-3xl rounded-2xl px-3 py-2.5 transition-shadow focus-within:shadow-glow-lg sm:px-4">
        {/* 图片预览 */}
        {pendingPreview && (
          <div className="mb-2 inline-flex animate-scale-in">
            <div className="relative">
              <img
                src={pendingPreview}
                alt="待发送"
                className="h-20 w-20 rounded-xl border border-[var(--glass-border-strong)] object-cover shadow-lift"
              />
              <button
                onClick={() => setPendingImage(null)}
                className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-ink/90 text-white shadow transition hover:scale-110"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}

        {recorder.isRecording ? (
          <div className="flex items-center gap-3 rounded-2xl border border-brand-200 bg-brand-50/70 px-4 py-3 dark:border-brand-500/25 dark:bg-brand-500/10">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-price opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-price" />
            </span>
            {/* 声浪柱：5 根 stagger */}
            <span className="flex h-5 items-center gap-[3px]">
              {[0, 1, 2, 3, 4].map((i) => (
                <span key={i} className="wave-bar h-full" style={{ animationDelay: `${i * 0.12}s` }} />
              ))}
            </span>
            <span className="flex-1 text-sm font-medium text-brand-700">
              正在录音 {recorder.seconds}s… 点击停止并发送
            </span>
            <button
              onClick={() => recorder.cancel()}
              className="rounded-lg px-3 py-1.5 text-sm text-ink-muted hover:bg-[var(--glass-bg-strong)]"
            >
              取消
            </button>
            <button
              onClick={stopVoice}
              className="gradient-brand flex h-9 w-9 items-center justify-center rounded-full text-white shadow-glow"
            >
              <Square size={16} className="fill-white" />
            </button>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <button
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-ink-muted transition hover:bg-brand-500/10 hover:text-brand-500 disabled:opacity-40"
              title="上传图片识别"
            >
              <ImagePlus size={20} />
            </button>
            <button
              onClick={startVoice}
              disabled={disabled || transcribing}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-ink-muted transition hover:bg-brand-500/10 hover:text-brand-500 disabled:opacity-40"
              title="语音输入"
            >
              <Mic size={20} className={transcribing ? 'animate-pulse text-brand-500' : ''} />
            </button>

            <div className="border-beam flex flex-1 items-end rounded-2xl bg-[var(--field-bg)] px-3 py-1.5 transition focus-within:bg-[var(--glass-bg-strong)]">
              <textarea
                ref={taRef}
                rows={1}
                value={text}
                onChange={(e) => {
                  setText(e.target.value)
                  autoGrow()
                }}
                onKeyDown={onKeyDown}
                onCompositionStart={() => {
                  composingRef.current = true
                }}
                onCompositionEnd={() => {
                  composingRef.current = false
                  compositionEndedAtRef.current = Date.now()
                }}
                placeholder={transcribing ? '正在识别语音…' : '和欧米说说你想买点什么～'}
                disabled={disabled || transcribing}
                className="max-h-[140px] w-full resize-none bg-transparent py-1.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-muted"
              />
            </div>

            <button
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                'flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white transition-all duration-200 active:scale-95',
                canSend ? 'gradient-brand shadow-glow hover:shadow-glow-lg' : 'bg-[var(--field-border)]',
              )}
            >
              <ArrowUp size={20} />
            </button>
          </div>
        )}

        {/* 底部工具行 */}
        <div className="mt-2 flex items-center justify-between px-1">
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setFastMode(!fastMode)}
              className={cn(
                'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-all duration-200',
                fastMode
                  ? 'bg-gradient-to-r from-amber-400 to-orange-400 text-white shadow-[0_2px_10px_rgba(251,191,36,0.4)]'
                  : 'text-ink-muted hover:bg-[var(--glass-bg-strong)] hover:text-ink-soft',
              )}
              title="快速模式：跳过部分推理，更快回复"
            >
              <Zap size={13} className={fastMode ? 'fill-white' : ''} />
              极速回答{fastMode ? '·开' : ''}
            </button>
            <button
              onClick={() => setDeepThink(!deepThink)}
              className={cn(
                'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-all duration-200',
                deepThink
                  ? 'bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white shadow-[0_2px_10px_rgba(139,92,246,0.45)]'
                  : 'text-ink-muted hover:bg-[var(--glass-bg-strong)] hover:text-ink-soft',
              )}
              title="深度思考：欧米自主多轮检索对比，更慢但更彻底"
            >
              <BrainCircuit size={13} className={deepThink ? 'animate-breathe' : ''} />
              深度思考{deepThink ? '·开' : ''}
            </button>
          </div>
          <span className="hidden text-[11px] text-ink-muted sm:inline">Enter 发送 · Shift+Enter 换行</span>
        </div>

        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickImage} />
      </div>
    </div>
  )
}
