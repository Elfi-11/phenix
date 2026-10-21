import { useEffect, useState } from 'react'
import TrafficChart from './TrafficChart'
import Assistant from './Assistant'

// Rafraîchissement : assez rapide pour voir en direct le passage OK -> panne -> OK pendant la démo
const REFRESH_MS = 5000
const GRAFANA_URL = 'http://localhost:3000/d/phenix-kpi-resilience?kiosk'

const SEVERITY_STYLE = {
  CRITICAL: 'bg-red-600 text-white',
  WARNING: 'bg-amber-400 text-black',
  INFO: 'bg-sky-500 text-white',
}

function formatTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString('fr-FR') : '—'
}

function Dashboard({ token }) {
  const [apiUp, setApiUp] = useState(null) 
  const [incidents, setIncidents] = useState([])
  const [lastCheck, setLastCheck] = useState(null)
  const [traffic, setTraffic] = useState([])
  const [trafficStale, setTrafficStale] = useState(false) 
  useEffect(() => {
    async function refresh() {
      // 1. État de l'API : /health traverse toute la chaîne (Caddy, WAF, nginx, backend)
      try {
        const res = await fetch('/health', { cache: 'no-store' })
        setApiUp(res.ok)
      } catch {
        setApiUp(false)
      }

      // 2. Incidents (réservé ADMIN) ; on garde l'ancienne liste si l'API ne répond pas
      try {
        const res = await fetch('/api/incidents', {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (res.ok) setIncidents(await res.json())
      } catch {
        // API injoignable : l'indicateur rouge suffit
      }

      // 3. Trafic (relayé depuis Prometheus par le backend)
      try {
        const res = await fetch('/api/metrics/traffic', {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (res.ok) {
          setTraffic(await res.json())
          setTrafficStale(false)
        } else {
          setTrafficStale(true)
        }
      } catch {
        setTrafficStale(true)
      }

      setLastCheck(new Date())
    }

    refresh()
    const id = setInterval(refresh, REFRESH_MS)
    // Arrête les appels quand on quitte la page
    return () => clearInterval(id)
  }, [token])

  const openIncidents = incidents.filter((i) => !i.resolved_at).length

  return (
    <div className="w-full max-w-5xl p-6 space-y-6">
      <h1 className="text-3xl font-bold text-white drop-shadow">Supervision Phenix</h1>

      {/* Indicateurs */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="p-5 rounded-2xl border-2 border-amber-50 bg-black/60 text-white">
          <p className="text-sm text-orange-100/80">API de paiement</p>
          <p className="mt-2 text-2xl font-bold">
            {apiUp === null ? 'Vérification…' : apiUp ? '🟢 Opérationnelle' : '🔴 Indisponible'}
          </p>
        </div>
        <div className="p-5 rounded-2xl border-2 border-amber-50 bg-black/60 text-white">
          <p className="text-sm text-orange-100/80">Incidents en cours</p>
          <p className="mt-2 text-2xl font-bold">{openIncidents}</p>
        </div>
        <div className="p-5 rounded-2xl border-2 border-amber-50 bg-black/60 text-white">
          <p className="text-sm text-orange-100/80">Dernière vérification</p>
          <p className="mt-2 text-2xl font-bold">{lastCheck ? lastCheck.toLocaleTimeString('fr-FR') : '—'}</p>
        </div>
      </div>

      {/* Trafic */}
      <div className="p-5 rounded-2xl border-2 border-amber-50 bg-[#1a1a19]/95 text-white">
        <h2 className="mb-3 text-xl font-semibold">Trafic de l'API</h2>
        <TrafficChart points={traffic} stale={trafficStale} />
      </div>

      {/* Incidents */}
      <div className="p-5 rounded-2xl border-2 border-amber-50 bg-black/60 text-white">
        <h2 className="mb-4 text-xl font-semibold">Incidents</h2>
        {incidents.length === 0 ? (
          <p className="text-orange-100/80">Aucun incident.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-orange-100/80 border-b border-amber-50/30">
                <tr>
                  <th className="py-2 pr-4">Détecté</th>
                  <th className="py-2 pr-4">Gravité</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Service</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Action</th>
                  <th className="py-2 pr-4">Reprise</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((i) => (
                  <tr key={i.id} className="border-b border-amber-50/10 align-top">
                    <td className="py-2 pr-4 whitespace-nowrap">{formatTime(i.detected_at)}</td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${SEVERITY_STYLE[i.severity]}`}>
                        {i.severity}
                      </span>
                    </td>
                    <td className="py-2 pr-4">{i.event_type}</td>
                    <td className="py-2 pr-4">{i.target_service ?? '—'}</td>
                    <td className="py-2 pr-4">{i.description}</td>
                    <td className="py-2 pr-4">{i.action_taken ?? '—'}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {i.resolved_at ? `✅ ${Math.round(i.recovery_seconds)} s` : '⏳ en cours'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Assistant RAG */}
      <Assistant token={token} />

      {/* Grafana : nouvel onglet (accessible seulement depuis le PC hôte, volontairement) */}
      <a
        href={GRAFANA_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block px-4 py-2.5 text-sm font-semibold text-white rounded-lg shadow-lg bg-linear-to-r from-red-700 to-orange-500 hover:from-red-800 hover:to-orange-600"
      >
        Ouvrir les métriques Grafana
      </a>
    </div>
  )
}

export default Dashboard
