import { useCallback, useEffect, useRef, useState } from 'react'

/** 选择浏览器支持的录音 MIME 类型。 */
function pickMime(): { mime: string; ext: string } {
  const candidates = [
    { mime: 'audio/webm;codecs=opus', ext: 'webm' },
    { mime: 'audio/webm', ext: 'webm' },
    { mime: 'audio/mp4', ext: 'mp4' },
    { mime: 'audio/ogg;codecs=opus', ext: 'ogg' },
  ]
  const MR = (window as unknown as { MediaRecorder?: typeof MediaRecorder }).MediaRecorder
  if (MR && typeof MR.isTypeSupported === 'function') {
    for (const c of candidates) {
      if (MR.isTypeSupported(c.mime)) return c
    }
  }
  return { mime: '', ext: 'webm' }
}

export interface VoiceRecorderApi {
  isRecording: boolean
  seconds: number
  supported: boolean
  start: () => Promise<boolean>
  stop: () => Promise<{ blob: Blob; filename: string } | null>
  cancel: () => void
}

/** 基于 MediaRecorder 的录音 hook，对应安卓端 VoiceRecorder.kt。 */
export function useVoiceRecorder(): VoiceRecorderApi {
  const [isRecording, setIsRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cancelledRef = useRef(false)
  const mimeRef = useRef<{ mime: string; ext: string }>({ mime: '', ext: 'webm' })

  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof (window as unknown as { MediaRecorder?: unknown }).MediaRecorder !== 'undefined'

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    recorderRef.current = null
    chunksRef.current = []
  }, [])

  const start = useCallback(async () => {
    if (!supported || isRecording) return false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const picked = pickMime()
      mimeRef.current = picked
      const rec = picked.mime
        ? new MediaRecorder(stream, { mimeType: picked.mime })
        : new MediaRecorder(stream)
      chunksRef.current = []
      cancelledRef.current = false
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.start()
      recorderRef.current = rec
      setIsRecording(true)
      setSeconds(0)
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
      return true
    } catch {
      cleanup()
      return false
    }
  }, [supported, isRecording, cleanup])

  const stop = useCallback(async () => {
    const rec = recorderRef.current
    if (!rec) {
      cleanup()
      setIsRecording(false)
      return null
    }
    return new Promise<{ blob: Blob; filename: string } | null>((resolve) => {
      rec.onstop = () => {
        const { mime, ext } = mimeRef.current
        const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' })
        cleanup()
        setIsRecording(false)
        if (cancelledRef.current || blob.size < 1200) {
          resolve(null)
          return
        }
        resolve({ blob, filename: `voice.${ext}` })
      }
      try {
        rec.stop()
      } catch {
        cleanup()
        setIsRecording(false)
        resolve(null)
      }
    })
  }, [cleanup])

  const cancel = useCallback(() => {
    cancelledRef.current = true
    try {
      recorderRef.current?.stop()
    } catch {
      /* ignore */
    }
    cleanup()
    setIsRecording(false)
  }, [cleanup])

  useEffect(() => () => {
    cancelledRef.current = true
    try { recorderRef.current?.stop() } catch { /* already stopped */ }
    cleanup()
  }, [cleanup])

  return { isRecording, seconds, supported, start, stop, cancel }
}
