import { useEffect } from 'react'
import { History, MessageSquare, Trash2, Plus } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { Modal } from '@/components/ui/Modal'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { relativeTime } from '@/lib/utils'

interface ConversationHistoryProps {
  open: boolean
  onClose: () => void
}

export function ConversationHistory({ open, onClose }: ConversationHistoryProps) {
  const conversations = useChatStore((s) => s.conversations)
  const isLoading = useChatStore((s) => s.isLoadingHistory)
  const currentId = useChatStore((s) => s.conversationId)
  const load = useChatStore((s) => s.loadConversations)
  const loadOne = useChatStore((s) => s.loadConversation)
  const del = useChatStore((s) => s.deleteConversation)
  const newConv = useChatStore((s) => s.newConversation)

  useEffect(() => {
    if (open) load()
  }, [open, load])

  return (
    <Modal open={open} onClose={onClose} title="历史对话" variant="right">
      <div className="flex h-full flex-col">
        <div className="p-3">
          <button
            onClick={() => {
              newConv()
              onClose()
            }}
            className="btn-primary w-full"
          >
            <Plus size={18} /> 开启新对话
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {isLoading ? (
            <LoadingBlock text="加载中…" />
          ) : conversations.length === 0 ? (
            <EmptyState
              icon={<History size={26} />}
              title="还没有历史对话"
              description="和欧米聊聊，记录会显示在这里"
            />
          ) : (
            <div className="space-y-1.5">
              {conversations.map((c) => (
                <div
                  key={c.conversation_id}
                  onClick={() => {
                    loadOne(c.conversation_id)
                    onClose()
                  }}
                  className={`group flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition ${
                    c.conversation_id === currentId
                      ? 'border-brand-300 bg-brand-50 dark:bg-brand-500/15'
                      : 'border-[var(--line)] bg-[var(--glass-bg)] backdrop-blur hover:border-brand-200 hover:shadow-glow'
                  }`}
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-500 dark:bg-brand-500/15 dark:text-brand-300">
                    <MessageSquare size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">
                      {c.title || c.last_message || '新对话'}
                    </p>
                    <p className="truncate text-xs text-ink-muted">
                      {relativeTime(c.updated_at || c.created_at)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      del(c.conversation_id)
                    }}
                    className="rounded-lg p-1.5 text-ink-muted opacity-0 transition hover:bg-rose-500/10 hover:text-rose-500 group-hover:opacity-100"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
