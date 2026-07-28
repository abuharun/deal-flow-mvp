import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SignalTag } from './ui'

describe('SignalTag', () => {
  it.each([
    ['high', 'High signal'],
    ['medium', 'Medium signal'],
    ['low', 'Low signal'],
  ] as const)('pairs the %s color with a text label and an icon', (signal, label) => {
    const { container } = render(<SignalTag signal={signal} />)
    // Text label is always present — color is never the only signal.
    expect(screen.getByText(label)).toBeInTheDocument()
    // A distinct icon shape accompanies it.
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.querySelector(`.tag-${signal}`)).not.toBeNull()
  })

  it('announces a partner re-tag to screen readers', () => {
    render(<SignalTag signal="high" overridden />)
    expect(screen.getByText(/re-tagged by the partner/)).toBeInTheDocument()
  })
})
