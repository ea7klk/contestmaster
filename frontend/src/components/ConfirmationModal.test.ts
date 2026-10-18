import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { expectAccessible } from '../test/a11y'
import ConfirmationModal from './ConfirmationModal.vue'

describe('ConfirmationModal', () => {
  it('requires the exact confirmation text and emits the entered value', async () => {
    const wrapper = mount(ConfirmationModal, {
      props: {
        open: true,
        title: 'Delete contest?',
        description: 'This cannot be undone.',
        confirmLabel: 'Delete',
        requiredText: 'radio-open',
        requiredTextLabel: 'Type radio-open to confirm.',
      },
    })
    await flushPromises()
    const dialog = document.body.querySelector('[role="alertdialog"]')!
    const input = document.body.querySelector<HTMLInputElement>(
      '[data-confirmation-input]',
    )!
    const confirm = document.body.querySelector<HTMLButtonElement>(
      'button[type="submit"]',
    )!

    expect(input).toBe(document.activeElement)
    expect(confirm.disabled).toBe(true)
    input.value = 'radio-closed'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    expect(confirm.disabled).toBe(true)
    input.value = 'radio-open'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    expect(confirm.disabled).toBe(false)
    await expectAccessible(dialog.cloneNode(true) as Element)
    document.body
      .querySelector('form')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    expect(wrapper.emitted('confirm')).toEqual([
      [{ confirmationText: 'radio-open', auditReason: '' }],
    ])
    wrapper.unmount()
  })

  it('emits cancel on Escape without confirming', async () => {
    const wrapper = mount(ConfirmationModal, {
      props: {
        open: true,
        title: 'Delete item?',
        description: 'This cannot be undone.',
        confirmLabel: 'Delete',
      },
    })
    await flushPromises()
    document.body
      .querySelector('[role="alertdialog"]')!
      .dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
      )

    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps keyboard focus inside the modal', async () => {
    const wrapper = mount(ConfirmationModal, {
      props: {
        open: true,
        title: 'Delete item?',
        description: 'This cannot be undone.',
        confirmLabel: 'Delete',
      },
    })
    await flushPromises()
    const cancel = document.body.querySelector<HTMLButtonElement>(
      '[data-cancel-button]',
    )!
    const confirm = document.body.querySelector<HTMLButtonElement>(
      'button[type="submit"]',
    )!

    document.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    )
    expect(document.activeElement).toBe(confirm)
    document.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Tab',
        bubbles: true,
        cancelable: true,
      }),
    )
    expect(document.activeElement).toBe(cancel)
    wrapper.unmount()
  })
})
