import { useState } from 'react'
import ConnectionsSettings from '../components/settings/ConnectionsSettings'
import TagsSettings from '../components/settings/TagsSettings'
import ManualPositionsSettings from '../components/settings/ManualPositionsSettings'

type SettingsTab = 'connections' | 'tags' | 'manual'

const TABS: { id: SettingsTab; label: string; glyph: string }[] = [
  { id: 'connections', label: 'Connections', glyph: '⬡' },
  { id: 'tags', label: 'Tags', glyph: '▣' },
  { id: 'manual', label: 'Manual', glyph: '✎' },
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
            Manage exchange credentials, wallets, conviction tags, and off-API positions for this
            local instance.
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

      {tab === 'connections' && <ConnectionsSettings />}
      {tab === 'tags' && <TagsSettings />}
      {tab === 'manual' && <ManualPositionsSettings />}
    </div>
  )
}
