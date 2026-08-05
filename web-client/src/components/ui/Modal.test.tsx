import { fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from './Modal'

describe('Modal', () => {
  it('announces itself, traps initial focus and restores focus', async () => {
    const close = vi.fn()
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const view = render(<Modal open onClose={close} title="确认操作"><button>确认</button></Modal>)
    expect(view.getByRole('dialog', { name: '确认操作' })).toBeInTheDocument()
    await waitFor(() => expect(view.getByRole('button', { name: '关闭' })).toHaveFocus())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(close).toHaveBeenCalledOnce()
    view.rerender(<Modal open={false} onClose={close} title="确认操作"><button>确认</button></Modal>)
    await waitFor(() => expect(opener).toHaveFocus())
    opener.remove()
  })

  it('cycles focus in both directions and supports titleless drawer variants', async () => {
    const close = vi.fn()
    const view = render(
      <Modal open onClose={close} variant="right" hideClose>
        <button>第一项</button><button>最后一项</button>
      </Modal>,
    )
    const dialog = view.getByRole('dialog', { name: '对话框' })
    const first = view.getByRole('button', { name: '第一项' })
    const last = view.getByRole('button', { name: '最后一项' })
    await waitFor(() => expect(first).toHaveFocus())
    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(first).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
    expect(dialog).toHaveClass('rounded-l-2xl')
    view.rerender(<Modal open onClose={close} variant="bottom" hideClose><span>内容</span></Modal>)
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(view.getByRole('dialog')).toHaveFocus()
    fireEvent.click(view.getByRole('button', { name: '关闭对话框' }))
    expect(close).toHaveBeenCalledOnce()
  })
})
