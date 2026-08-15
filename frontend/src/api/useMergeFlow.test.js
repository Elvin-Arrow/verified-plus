import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMergeFlow } from './useMergeFlow.js'
import * as api from './client.js'

vi.mock('./client.js')

afterEach(() => vi.resetAllMocks())

/**
 * docs/ui-spec.md §5.1: clicking a list-view Merge affordance must open a
 * confirmation showing both sides BEFORE calling POST /api/requests/{id}/merge
 * -- never merge immediately on click. Since RequestSummary (api-spec.md §1.3)
 * only carries a cheap has_suggested_merge boolean (not the target/distance),
 * this hook fetches GET /api/requests/{id} on click to get the real
 * suggested_merges entry, THEN shows the confirmation.
 */
describe('useMergeFlow', () => {
  it('starts with no pending confirmation', () => {
    const { result } = renderHook(() => useMergeFlow(async (fn) => fn()))
    expect(result.current.mergingTarget).toBeNull()
  })

  it('fetches request detail and opens the confirmation on openMergeConfirm, without calling merge yet', async () => {
    api.getRequestDetail.mockResolvedValue({
      id: 'req_a',
      suggested_merges: [{ target_event_id: 'evt_far', distance_km: 1.9 }],
    })
    const { result } = renderHook(() => useMergeFlow(async (fn) => fn()))

    await act(async () => {
      await result.current.openMergeConfirm('req_a')
    })

    expect(api.getRequestDetail).toHaveBeenCalledWith('req_a')
    expect(result.current.mergingTarget).toEqual({
      requestId: 'req_a',
      target_event_id: 'evt_far',
      distance_km: 1.9,
    })
    expect(api.mergeRequest).not.toHaveBeenCalled()
  })

  it('does nothing if the request has no suggested_merges entry (stale click)', async () => {
    api.getRequestDetail.mockResolvedValue({ id: 'req_a', suggested_merges: [] })
    const { result } = renderHook(() => useMergeFlow(async (fn) => fn()))

    await act(async () => {
      await result.current.openMergeConfirm('req_a')
    })

    expect(result.current.mergingTarget).toBeNull()
  })

  it('calls mergeRequest with the right target on confirmMerge, then clears the pending state', async () => {
    api.getRequestDetail.mockResolvedValue({
      id: 'req_a',
      suggested_merges: [{ target_request_id: 'req_other', distance_km: 1.2 }],
    })
    api.mergeRequest.mockResolvedValue({})
    const runAction = vi.fn(async (fn) => fn())
    const { result } = renderHook(() => useMergeFlow(runAction))

    await act(async () => {
      await result.current.openMergeConfirm('req_a')
    })
    await act(async () => {
      await result.current.confirmMerge()
    })

    expect(runAction).toHaveBeenCalled()
    expect(api.mergeRequest).toHaveBeenCalledWith('req_a', {
      actor: expect.any(String),
      targetEventId: null,
      targetRequestId: 'req_other',
    })
    expect(result.current.mergingTarget).toBeNull()
  })

  it('cancelMerge clears the pending confirmation without calling merge', async () => {
    api.getRequestDetail.mockResolvedValue({
      id: 'req_a',
      suggested_merges: [{ target_event_id: 'evt_far', distance_km: 1.9 }],
    })
    const { result } = renderHook(() => useMergeFlow(async (fn) => fn()))

    await act(async () => {
      await result.current.openMergeConfirm('req_a')
    })
    act(() => {
      result.current.cancelMerge()
    })

    expect(result.current.mergingTarget).toBeNull()
    expect(api.mergeRequest).not.toHaveBeenCalled()
  })
})
