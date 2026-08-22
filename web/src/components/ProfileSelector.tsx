import { useEffect, useState } from 'react'
import { getProfiles, setProfile } from '../api'
import type { DeviceProfile } from '../types'
import './ProfileSelector.css'

interface Props {
  currentProfile: DeviceProfile | null
  onProfileChanged: (profile: DeviceProfile) => void
}

export default function ProfileSelector({ currentProfile, onProfileChanged }: Props) {
  const [profiles, setProfiles] = useState<DeviceProfile[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let alive = true
    getProfiles()
      .then((list) => { if (alive) setProfiles(list) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const onChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    if (!id || id === currentProfile?.id) return
    setLoading(true)
    try {
      const p = await setProfile(id)
      onProfileChanged(p)
    } catch (err) {
      alert(`Erreur changement de profil : ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  if (profiles.length <= 1) return null

  return (
    <div className="profileSelector" title="Changer le type d'appareil Aldes">
      <label className="profileLabel">Appareil</label>
      <select
        className="profileSelect"
        value={currentProfile?.id ?? ''}
        onChange={onChange}
        disabled={loading}
      >
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  )
}
