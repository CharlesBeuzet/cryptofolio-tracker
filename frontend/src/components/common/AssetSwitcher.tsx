import { useEffect, useRef, useState } from 'react'
import { assetColor } from '../../utils/format'
import type { GroupedAsset } from '../../utils/groupPositionsByAsset'

interface AssetSwitcherProps {
  assets: GroupedAsset[]
  currentSymbol: string
  onSelect: (symbol: string) => void
}

export default function AssetSwitcher({ assets, currentSymbol, onSelect }: AssetSwitcherProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const current = currentSymbol.toUpperCase()
  const currentIndex = assets.findIndex((asset) => asset.symbol === current)

  useEffect(() => {
    if (!open) return

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }

    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  if (assets.length < 2) return null

  return (
    <div ref={rootRef} className="panel !py-0 !px-0 overflow-hidden mb-[18px]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls="asset-switcher-list"
        className="w-full flex items-center gap-2.5 px-4 py-2.5 sm:px-[15px] sm:py-2 min-h-[40px] sm:min-h-0 text-left bg-transparent border-0 cursor-pointer text-inherit"
      >
        <span
          className={`font-mono text-sillage-soft text-xs shrink-0 transition-transform duration-200 ${
            open ? 'rotate-90' : ''
          }`}
          aria-hidden
        >
          ›
        </span>
        {currentIndex >= 0 && (
          <span className="sw" style={{ background: assetColor(currentIndex) }} />
        )}
        <span className="font-mono text-xs text-sillage-ink">{current}</span>
        <span className="chip shrink-0">
          {assets.length} asset{assets.length === 1 ? '' : 's'}
        </span>
      </button>

      {open && (
        <div
          id="asset-switcher-list"
          role="listbox"
          aria-label="Assets"
          className="border-t border-sillage-line px-2 py-2 max-h-[240px] overflow-y-auto flex flex-col gap-1"
        >
          {assets.map((asset, index) => {
            const selected = asset.symbol === current
            return (
              <button
                key={asset.symbol}
                type="button"
                role="option"
                aria-selected={selected}
                className={`atab w-full justify-start ${selected ? 'on' : ''}`}
                onClick={() => {
                  setOpen(false)
                  if (!selected) onSelect(asset.symbol)
                }}
              >
                <span className="sw" style={{ background: assetColor(index) }} />
                {asset.symbol}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
