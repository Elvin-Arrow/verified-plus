import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useActionErrorHandling } from './useActionErrorHandling.js'

describe('useActionErrorHandling (FE-13, §11)', () => {
  it('refetches and never sets toast/banner on success', async () => {
    const refetch = vi.fn().mockResolvedValue()
    const { result } = renderHook(() => useActionErrorHandling(refetch))
    await act(async () => {
      await result.current.runAction(() => Promise.resolve())
    })
    expect(refetch).toHaveBeenCalledTimes(1)
    expect(result.current.toast).toBeNull()
    expect(result.current.bannerError).toBeNull()
  })

  it('shows the stale-view toast and refetches on a 404', async () => {
    const refetch = vi.fn().mockResolvedValue()
    const { result } = renderHook(() => useActionErrorHandling(refetch))
    await act(async () => {
      await result.current.runAction(() => Promise.reject(Object.assign(new Error('gone'), { status: 404, code: 'NOT_FOUND' })))
    })
    expect(result.current.toast).toMatch(/this item has changed/i)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('shows the same toast pattern and refetches on a 409', async () => {
    const refetch = vi.fn().mockResolvedValue()
    const { result } = renderHook(() => useActionErrorHandling(refetch))
    await act(async () => {
      await result.current.runAction(() => Promise.reject(Object.assign(new Error('stale'), { status: 409, code: 'INVALID_STATE_TRANSITION' })))
    })
    expect(result.current.toast).toMatch(/this item has changed/i)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('sets a persistent banner (not a toast, no auto-refetch) on a 500', async () => {
    const refetch = vi.fn().mockResolvedValue()
    const { result } = renderHook(() => useActionErrorHandling(refetch))
    await act(async () => {
      await result.current.runAction(() => Promise.reject(Object.assign(new Error('boom'), { status: 500, code: 'INTERNAL_ERROR' })))
    })
    expect(result.current.bannerError).toBeInstanceOf(Error)
    expect(result.current.toast).toBeNull()
    expect(refetch).not.toHaveBeenCalled()
  })

  it('retryBanner clears the banner and refetches', async () => {
    const refetch = vi.fn().mockResolvedValue()
    const { result } = renderHook(() => useActionErrorHandling(refetch))
    await act(async () => {
      await result.current.runAction(() => Promise.reject(Object.assign(new Error('boom'), { status: 500, code: 'INTERNAL_ERROR' })))
    })
    act(() => {
      result.current.retryBanner()
    })
    expect(result.current.bannerError).toBeNull()
    expect(refetch).toHaveBeenCalledTimes(1)
  })
})
