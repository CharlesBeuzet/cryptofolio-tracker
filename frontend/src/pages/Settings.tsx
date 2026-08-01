import { useState } from 'react'
import ConnectionsSettings from '../components/settings/ConnectionsSettings'
import TagsSettings from '../components/settings/TagsSettings'

type SettingsTab = 'connections' | 'tags'

const TABS: { id: SettingsTab; label: string; glyph: string }[] = [
  { id: 'connections', label: 'Connections', glyph: '⬡' },
  { id: 'tags', label: 'Tags', glyph: '▣' },
]

export default function Settings() {
  const [tab, setTab] = useState<SettingsTab>('connections')

  return (
    <div>
      <div className="flex flex-wrap justify-between items-end gap-4 mb-[18px]">
        <div>
          <div className="lbl">§5 · Settings</div>
          <div className="font-serif text-[26px] leading-none mt-[7px]">Instance preferences</div>
          <p className="cap mt-2 max-w-xl">
            Manage exchange credentials, wallets, and upcoming position tags for this local instance.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`atab ${tab === item.id ? 'on' : ''}`}
              onClick={() => setTab(item.id)}
            >
              <span className="text-sillage-green">{item.glyph}</span>
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'connections' ? <ConnectionsSettings /> : <TagsSettings />}
import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@apollo/client'
import { GET_PORTFOLIO, GET_TAGS } from '../graphql/queries'
import { CREATE_TAG, DELETE_TAG, SET_POSITION_TAG, UPDATE_TAG } from '../graphql/mutations'
import { assetColor } from '../utils/format'

interface Tag {
  id: number
  name: string
  description: string | null
}

interface PositionRow {
  id: number
  symbol: string
  exchange: string | null
  value: number
  tag: Tag | null
}

export default function Settings() {
  const { data: tagsData, loading: tagsLoading, refetch: refetchTags } = useQuery(GET_TAGS)
  const { data: portfolioData, loading: portfolioLoading, refetch: refetchPortfolio } =
    useQuery(GET_PORTFOLIO)

  const [createTag] = useMutation(CREATE_TAG)
  const [updateTag] = useMutation(UPDATE_TAG)
  const [deleteTag] = useMutation(DELETE_TAG)
  const [setPositionTag] = useMutation(SET_POSITION_TAG)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const tags: Tag[] = tagsData?.tags ?? []
  const positions: PositionRow[] = useMemo(() => {
    const list = portfolioData?.portfolio?.positions ?? []
    return [...list].sort((a: PositionRow, b: PositionRow) => {
      const sym = a.symbol.localeCompare(b.symbol)
      if (sym !== 0) return sym
      return (a.exchange || '').localeCompare(b.exchange || '')
    })
  }, [portfolioData])

  const refresh = async () => {
    await Promise.all([refetchTags(), refetchPortfolio()])
  }

  const onCreate = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('Tag name is required')
      return
    }
    setBusy(true)
    try {
      await createTag({
        variables: {
          name: name.trim(),
          description: description.trim() || null,
        },
      })
      setName('')
      setDescription('')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create tag')
    } finally {
      setBusy(false)
    }
  }

  const onRename = async (tag: Tag) => {
    const next = window.prompt('Rename tag', tag.name)
    if (next == null || next.trim() === tag.name) return
    setError(null)
    setBusy(true)
    try {
      await updateTag({ variables: { id: tag.id, name: next.trim() } })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update tag')
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (tag: Tag) => {
    if (!window.confirm(`Delete tag “${tag.name}”? Positions will become untagged.`)) return
    setError(null)
    setBusy(true)
    try {
      await deleteTag({ variables: { id: tag.id } })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete tag')
    } finally {
      setBusy(false)
    }
  }

  const onAssign = async (positionId: number, tagId: number | null) => {
    setError(null)
    setBusy(true)
    try {
      await setPositionTag({ variables: { positionId, tagId } })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign tag')
    } finally {
      setBusy(false)
    }
  }

  if (tagsLoading || portfolioLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading settings…</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-end mb-[18px]">
        <div>
          <div className="lbl">§5 · Settings</div>
          <div className="font-serif text-[26px] leading-none mt-[7px]">Conviction tags</div>
        </div>
        <div className="cap max-w-sm text-right">
          Tag each asset×exchange position — track VC plays and backspots separately on Theses.
        </div>
      </div>

      {error && (
        <div className="panel mb-4 text-sillage-down font-mono text-xs">{error}</div>
      )}

      <div className="flex gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel w-full lg:w-[320px] flex-shrink-0">
          <div className="lbl mb-3">New tag</div>
          <form onSubmit={onCreate} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. VC play"
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                disabled={busy}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Description</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional thesis note"
                rows={3}
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green resize-none"
                disabled={busy}
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="font-mono text-[11px] tracking-wide uppercase border border-sillage-green text-sillage-green rounded-lg px-3 py-2 hover:bg-sillage-gsoft transition-colors disabled:opacity-50"
            >
              Create tag
            </button>
          </form>

          <div className="rule my-4" />
          <div className="lbl mb-2">Catalog</div>
          {tags.length === 0 ? (
            <div className="text-sillage-soft text-sm">No tags yet.</div>
          ) : (
            <div className="flex flex-col gap-2">
              {tags.map((tag, i) => (
                <div
                  key={tag.id}
                  className="flex items-start gap-2 border border-sillage-line rounded-lg px-3 py-2.5"
                >
                  <span
                    className="sw w-[10px] h-[10px] mt-1 flex-shrink-0"
                    style={{ background: assetColor(i) }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-xs font-semibold">{tag.name}</div>
                    {tag.description && (
                      <div className="cap mt-1 leading-normal">{tag.description}</div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      className="font-mono text-[9px] text-sillage-soft hover:text-sillage-ink"
                      onClick={() => onRename(tag)}
                      disabled={busy}
                    >
                      rename
                    </button>
                    <button
                      type="button"
                      className="font-mono text-[9px] text-sillage-down hover:opacity-80"
                      onClick={() => onDelete(tag)}
                      disabled={busy}
                    >
                      delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel flex-1 min-w-0">
          <div className="flex justify-between items-baseline mb-1">
            <div className="lbl">Assign by position</div>
            <div className="cap">one tag per asset × venue</div>
          </div>

          {positions.length === 0 ? (
            <div className="text-center py-10 text-sillage-soft text-sm">No open positions.</div>
          ) : (
            <>
              <div className="trow text-sillage-soft border-t-0">
                <div className="w-20 lbl text-[9px]">Asset</div>
                <div className="w-28 lbl text-[9px]">Venue</div>
                <div className="flex-1 lbl text-[9px]">Tag</div>
              </div>
              {positions.map((p) => (
                <div key={p.id} className="trow items-center">
                  <div className="w-20 tk">{p.symbol}</div>
                  <div className="w-28">
                    <span className="chip">{p.exchange || 'other'}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <select
                      className="w-full max-w-xs bg-transparent border border-sillage-line rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-sillage-ink outline-none focus:border-sillage-green"
                      value={p.tag?.id ?? ''}
                      disabled={busy || tags.length === 0}
                      onChange={(e) => {
                        const raw = e.target.value
                        onAssign(p.id, raw === '' ? null : parseInt(raw, 10))
                      }}
                    >
                      <option value="">Untagged</option>
                      {tags.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </>
          )}

          {tags.length === 0 && positions.length > 0 && (
            <div className="cap mt-4">Create a tag on the left before assigning positions.</div>
          )}
        </div>
      </div>
    </div>
  )
}
