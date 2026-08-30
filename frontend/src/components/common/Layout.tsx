import { ReactNode, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { GET_PORTFOLIO, GET_SYNCED_VENUES } from '../../graphql/queries'
import { useTheme } from '../../context/ThemeContext'
import { formatPct, formatUsd, pnlColorClass } from '../../utils/format'
import { excludeCashLikePositions } from '../../utils/cashLikeAssets'
import { groupPositionsByAsset, type PositionLike } from '../../utils/groupPositionsByAsset'
import Logo from './Logo'

interface LayoutProps {
  children: ReactNode
}

interface SyncedVenue {
  key: string
  displayName: string
  kind: string
}

const NAV_ITEMS = [
  { path: '/', label: 'Overview', glyph: '◇', num: '§1', match: (p: string) => p === '/' },
  {
    path: '/position',
    label: 'Positions',
    glyph: '▮',
    num: '§2',
    match: (p: string) => p.startsWith('/position') || p.startsWith('/asset'),
  },
  { path: '/fiat-deposits', label: 'On-ramp', glyph: '$', num: '§3', match: (p: string) => p === '/fiat-deposits' },
  { path: '/performance', label: 'Theses', glyph: '§', num: '§4', match: (p: string) => p === '/performance' },
  { path: '/settings', label: 'Settings', glyph: '⚙', num: '§5', match: (p: string) => p === '/settings' },
]

function venueLines(venues: SyncedVenue[]): string[] {
  const exchanges = venues
    .filter((v) => v.kind === 'exchange')
    .map((v) => v.displayName)
  const wallets = venues
    .filter((v) => v.kind === 'wallet')
    .map((v) => v.displayName)

  const lines: string[] = []
  if (exchanges.length) lines.push(exchanges.join(' · '))
  if (wallets.length) lines.push(wallets.join(' · '))
  return lines
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const { theme, toggleTheme, themeGlyph } = useTheme()
  const { data } = useQuery(GET_PORTFOLIO)
  const [navOpen, setNavOpen] = useState(false)
  const { data: venuesData } = useQuery(GET_SYNCED_VENUES)

  const portfolio = data?.portfolio
  const totalValue = portfolio?.totalValue ?? 0
  const pnlPercent = portfolio?.todaysPnlPercent ?? 0
  const isPositive = pnlPercent >= 0

  const venues: SyncedVenue[] = venuesData?.syncedVenues ?? []
  const lines = venueLines(venues)
  const venueCount = venues.length

  const now = new Date()
  const dateStr = now
    .toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase()
  const timeStr = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC'

  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [navOpen])

const navLinks = (
    <>
      <nav className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const active = item.match(location.pathname)
          return (
            <Link
              key={item.path}
              to={(() => {
                if (item.path !== '/position' || !portfolio?.positions?.length) return item.path
                const top = groupPositionsByAsset(
                  excludeCashLikePositions(portfolio.positions as PositionLike[]),
                )[0]?.symbol
                return top ? `/asset/${encodeURIComponent(top)}` : item.path
              })()}
              className={`navi no-underline ${active ? 'on' : ''}`}
              onClick={() => setNavOpen(false)}
            >
              <span className="w-[18px] text-center text-sillage-green text-[13px]">{item.glyph}</span>
              <span className="flex-1">{item.label}</span>
              <span className="lbl text-[9px]">{item.num}</span>
            </Link>
          )
        })}
      </nav>

      <div className="flex-1" />

      <div className="rule" />
      <div className="pt-3.5 px-1.5 pb-1">
        <div className="lbl mb-2">
          Venues · {venueCount > 0 ? `${venueCount} synced` : 'synced'}
        </div>
        <div className="font-mono text-[11px] text-sillage-soft flex flex-col gap-1.5">
          {lines.length > 0 ? (
            lines.map((line) => <span key={line}>◉ {line}</span>)
          ) : (
            <span>◉ No providers configured</span>
          )}
        </div>
      </div>
      <div className="font-mono text-[9px] text-sillage-soft pt-3.5 px-2 tracking-wide">
        ⬡ keys encrypted on-device
      </div>
    </>
  )

  return (
    <div
      className={`min-h-[100dvh] w-full max-w-full flex font-serif text-sillage-ink ${theme === 'dark' ? 'dark' : 'light'}`}
    >
      {/* Tablet / desktop sidebar */}
      <aside className="hidden md:flex w-[212px] flex-shrink-0 border-r border-sillage-line px-4 py-5 flex-col bg-sillage-card2">
        <div className="flex items-center gap-2.5 px-1.5 pb-[22px]">
          <Logo />
          <div className="font-serif font-semibold text-base tracking-wide">SILLAGE</div>
        </div>
        {navLinks}
      </aside>

      {/* Phone drawer */}
      {navOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button
            type="button"
            className="absolute inset-0 bg-black/45 border-0 cursor-pointer"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
          />
          <aside className="absolute left-0 top-0 bottom-0 w-[min(300px,88vw)] flex flex-col border-r border-sillage-line px-4 py-5 bg-sillage-card2 shadow-xl animate-[slideIn_0.2s_ease-out]">
            <div className="flex items-center justify-between gap-2 px-1.5 pb-[22px]">
              <div className="flex items-center gap-2.5">
                <Logo />
                <div className="font-serif font-semibold text-base tracking-wide">SILLAGE</div>
              </div>
              <button
                type="button"
                className="iconbtn"
                aria-label="Close menu"
                onClick={() => setNavOpen(false)}
              >
                ✕
              </button>
            </div>
            {navLinks}
          </aside>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col h-[100dvh] max-w-full">
        <header className="flex-shrink-0 border-b border-sillage-line px-3 sm:px-5 md:px-[26px] min-h-[56px] md:h-[60px] py-2 md:py-0 flex flex-wrap justify-between items-center gap-x-3 gap-y-2 bg-sillage-card2">
          <div className="flex items-center gap-2.5 min-w-0">
            <button
              type="button"
              className="iconbtn md:hidden flex-shrink-0"
              aria-label="Open menu"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              ☰
            </button>
            <div className="font-mono text-[11px] text-sillage-soft flex items-center gap-2 sm:gap-3.5 min-w-0">
              <span className="text-sillage-green flex-shrink-0">◉</span>
              <span className="truncate">local instance</span>
              <span className="opacity-40 hidden lg:inline">·</span>
              <span className="hidden lg:inline whitespace-nowrap">
                {dateStr} · {timeStr}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 sm:gap-[18px] ml-auto">
            <div className="text-right">
              <div className="lbl text-[9px] hidden sm:block">Net asset value</div>
              <div className="font-mono tabular-nums font-semibold text-[15px] sm:text-[17px]">
                {formatUsd(totalValue)}
              </div>
            </div>
            <div
              className={`font-mono text-[11px] sm:text-xs border border-sillage-green rounded-[20px] px-2 sm:px-2.5 py-1 tabular-nums whitespace-nowrap ${pnlColorClass(pnlPercent)}`}
            >
              {isPositive ? '▲' : '▼'} {formatPct(pnlPercent, false)}
            </div>
            <button type="button" className="iconbtn" onClick={toggleTheme} aria-label="Toggle theme">
              {themeGlyph}
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-auto px-3 sm:px-5 md:px-6 lg:px-[30px] py-4 sm:py-5 lg:py-[26px] w-full max-w-full">
          {children}
        </main>
      </div>
    </div>
  )
}
