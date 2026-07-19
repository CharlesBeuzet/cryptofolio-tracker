import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { GET_PORTFOLIO, GET_SYNCED_VENUES } from '../../graphql/queries'
import { useTheme } from '../../context/ThemeContext'
import { formatPct, formatUsd, pnlColorClass } from '../../utils/format'
import { groupPositionsByAsset } from '../../utils/groupPositionsByAsset'
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

  return (
    <div className={`min-h-screen flex font-serif text-sillage-ink ${theme === 'dark' ? 'dark' : 'light'}`}>
      <aside className="w-[212px] flex-shrink-0 border-r border-sillage-line px-4 py-5 flex flex-col bg-sillage-card2">
        <div className="flex items-center gap-2.5 px-1.5 pb-[22px]">
          <Logo />
          <div className="font-serif font-semibold text-base tracking-wide">SILLAGE</div>
        </div>

        <nav className="flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const active = item.match(location.pathname)
            return (
              <Link
                key={item.path}
                to={(() => {
                  if (item.path !== '/position' || !portfolio?.positions?.length) return item.path
                  const top = groupPositionsByAsset(portfolio.positions)[0]?.symbol
                  return top ? `/asset/${encodeURIComponent(top)}` : item.path
                })()}
                className={`navi no-underline ${active ? 'on' : ''}`}
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
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-screen">
        <header className="flex-shrink-0 border-b border-sillage-line px-[26px] h-[60px] flex justify-between items-center bg-sillage-card2">
          <div className="font-mono text-[11px] text-sillage-soft flex items-center gap-3.5">
            <span className="text-sillage-green">◉</span>
            local instance
            <span className="opacity-40">·</span>
            {dateStr} · {timeStr}
          </div>
          <div className="flex items-center gap-[18px]">
            <div className="text-right">
              <div className="lbl text-[9px]">Net asset value</div>
              <div className="font-mono tabular-nums font-semibold text-[17px]">{formatUsd(totalValue)}</div>
            </div>
            <div
              className={`font-mono text-xs border border-sillage-green rounded-[20px] px-2.5 py-1 tabular-nums ${pnlColorClass(pnlPercent)}`}
            >
              {isPositive ? '▲' : '▼'} {formatPct(pnlPercent, false)}
            </div>
            <button type="button" className="iconbtn" onClick={toggleTheme} aria-label="Toggle theme">
              {themeGlyph}
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-auto px-[30px] py-[26px]">{children}</main>
      </div>
    </div>
  )
}
