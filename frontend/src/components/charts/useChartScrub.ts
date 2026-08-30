import { useCallback, useRef, type DragEvent, type MouseEvent, type PointerEvent } from 'react'
import {
  indexFromRatio,
  ratioFromClientX,
  type PlotBounds,
} from './nearestChartIndex'

const LOCK_PX = 8

type GestureLock = 'none' | 'pending' | 'scrub' | 'scroll'

interface UseChartScrubOptions {
  pointCount: number
  onIndex: (index: number | null) => void
  plotBounds?: PlotBounds | null
  getIndex?: (ratio: number) => number
}

function isHoverPointer(pointerType: string): boolean {
  return pointerType === 'mouse' || pointerType === 'pen' || pointerType === ''
}

/**
 * Pointer scrub for charts: hover-to-inspect on mouse, tap/horizontal-drag on
 * touch (sticky after lift). Vertical touch movement yields to page scroll.
 */
export function useChartScrub({
  pointCount,
  onIndex,
  plotBounds,
  getIndex,
}: UseChartScrubOptions) {
  const rootRef = useRef<HTMLDivElement>(null)
  const lockRef = useRef<GestureLock>('none')
  const startRef = useRef({ x: 0, y: 0 })
  const onIndexRef = useRef(onIndex)
  const getIndexRef = useRef(getIndex)
  const plotBoundsRef = useRef(plotBounds)
  const pointCountRef = useRef(pointCount)

  onIndexRef.current = onIndex
  getIndexRef.current = getIndex
  plotBoundsRef.current = plotBounds
  pointCountRef.current = pointCount

  const inspectAt = useCallback((clientX: number) => {
    const el = rootRef.current
    const count = pointCountRef.current
    if (!el || count <= 0) return

    const ratio = ratioFromClientX(clientX, el.getBoundingClientRect(), plotBoundsRef.current)
    const resolve = getIndexRef.current
    const index = resolve ? resolve(ratio) : indexFromRatio(count, ratio)
    onIndexRef.current(index)
  }, [])

  const releaseCapture = useCallback((pointerId: number) => {
    const el = rootRef.current
    if (el?.hasPointerCapture(pointerId)) {
      el.releasePointerCapture(pointerId)
    }
  }, [])

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.pointerType === 'touch') {
        lockRef.current = 'pending'
        startRef.current = { x: event.clientX, y: event.clientY }
        return
      }
      inspectAt(event.clientX)
    },
    [inspectAt],
  )

  const onPointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.pointerType !== 'touch') {
        inspectAt(event.clientX)
        return
      }

      const dx = event.clientX - startRef.current.x
      const dy = event.clientY - startRef.current.y

      if (lockRef.current === 'pending') {
        if (Math.abs(dx) < LOCK_PX && Math.abs(dy) < LOCK_PX) return
        if (Math.abs(dy) > Math.abs(dx)) {
          lockRef.current = 'scroll'
          return
        }
        lockRef.current = 'scrub'
        event.currentTarget.setPointerCapture(event.pointerId)
        event.preventDefault()
        inspectAt(event.clientX)
        return
      }

      if (lockRef.current === 'scrub') {
        event.preventDefault()
        inspectAt(event.clientX)
      }
    },
    [inspectAt],
  )

  const onPointerUp = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.pointerType === 'touch' && lockRef.current === 'pending') {
        inspectAt(event.clientX)
      }
      lockRef.current = 'none'
      releaseCapture(event.pointerId)
    },
    [inspectAt, releaseCapture],
  )

  const onPointerCancel = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      lockRef.current = 'none'
      releaseCapture(event.pointerId)
    },
    [releaseCapture],
  )

  const onPointerLeave = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (!isHoverPointer(event.pointerType)) return
    if (event.buttons !== 0) return
    onIndexRef.current(null)
  }, [])

  const onContextMenu = useCallback((event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
  }, [])

  const onDragStart = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
  }, [])

  return {
    ref: rootRef,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onPointerLeave,
    onContextMenu,
    onDragStart,
  }
}
