import { useRef, useState } from 'react'

// Couleurs de séries validées pour fond sombre (bleu = slot 1, orange = slot 2)
const SERIES = [
  { key: 'total', label: 'Requêtes', color: '#3987e5' },
  { key: 'errors', label: 'Erreurs (4xx/5xx)', color: '#d95926' },
]
const INK = { primary: '#f0efec', secondary: '#c3c2b7', muted: '#898781', grid: '#2c2c2a', axis: '#383835' }

// Zone de dessin (unités du viewBox)
const W = 640
const H = 220
const M = { top: 12, right: 110, bottom: 26, left: 44 }
const PW = W - M.left - M.right
const PH = H - M.top - M.bottom

function niceMax(v) {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v))
  return [1, 2, 5, 10].map((n) => n * p).find((n) => n >= v)
}

const hhmm = (t) => new Date(t * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
const fmt = (v) => v.toLocaleString('fr-FR', { maximumFractionDigits: 2 })

function TrafficChart({ points, stale }) {
  const svgRef = useRef(null)
  const [hover, setHover] = useState(null) // index du point survolé

  if (points.length < 2) {
    return <p className="text-sm" style={{ color: INK.secondary }}>Pas encore assez de données (attendre ~1 min).</p>
  }

  const t0 = points[0].t
  const t1 = points[points.length - 1].t
  const yMax = niceMax(Math.max(...points.map((p) => p.total)))
  const x = (t) => M.left + ((t - t0) / (t1 - t0)) * PW
  const y = (v) => M.top + PH - (v / yMax) * PH
  const path = (key) => points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p[key]).toFixed(1)}`).join('')

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax)
  const xTicks = [0, 1 / 3, 2 / 3, 1].map((f) => points[Math.round(f * (points.length - 1))].t)

  // Étiquettes directes en bout de ligne, écartées si elles se chevauchent
  const last = points[points.length - 1]
  const labelY = SERIES.map((s) => y(last[s.key]))
  if (Math.abs(labelY[0] - labelY[1]) < 14) {
    const mid = (labelY[0] + labelY[1]) / 2
    labelY[0] = mid - 7
    labelY[1] = mid + 7
  }

  // Le réticule cherche le X le plus proche du pointeur : pas besoin de viser la ligne
  function onMove(e) {
    const r = svgRef.current.getBoundingClientRect()
    const vx = ((e.clientX - r.left) / r.width) * W
    const t = t0 + ((vx - M.left) / PW) * (t1 - t0)
    let best = 0
    points.forEach((p, i) => {
      if (Math.abs(p.t - t) < Math.abs(points[best].t - t)) best = i
    })
    setHover(best)
  }

  const hp = hover !== null ? points[hover] : null

  return (
    <div className="relative" style={{ opacity: stale ? 0.5 : 1 }}>
      {/* Légende (toujours présente pour 2 séries) */}
      <div className="flex gap-5 mb-2 text-sm" style={{ color: INK.secondary }}>
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-2">
            <span className="inline-block w-4 h-0.5 rounded" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span style={{ color: INK.muted }}>req/s · 15 dernières minutes</span>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto touch-none"
        role="img"
        aria-label="Trafic de l'API : requêtes et erreurs par seconde sur 15 minutes"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={M.left + PW} y1={y(v)} y2={y(v)} stroke={v === 0 ? INK.axis : INK.grid} strokeWidth="1" />
            <text x={M.left - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill={INK.muted} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {fmt(v)}
            </text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={i} x={x(t)} y={H - 6} textAnchor={i === 0 ? 'start' : i === 3 ? 'end' : 'middle'} fontSize="11" fill={INK.muted}>
            {hhmm(t)}
          </text>
        ))}

        {SERIES.map((s) => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        ))}

        {SERIES.map((s, i) => (
          <text key={s.key} x={M.left + PW + 8} y={labelY[i] + 4} fontSize="12" fill={INK.secondary}>
            {s.label.split(' ')[0]} {fmt(last[s.key])}
          </text>
        ))}

        {hp && (
          <g>
            <line x1={x(hp.t)} x2={x(hp.t)} y1={M.top} y2={M.top + PH} stroke={INK.secondary} strokeWidth="1" />
            {SERIES.map((s) => (
              <circle key={s.key} cx={x(hp.t)} cy={y(hp[s.key])} r="4" fill={s.color} stroke="#1a1a19" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>

      {/* Infobulle : toutes les séries au X survolé, valeur en avant */}
      {hp && (
        <div
          className="absolute top-8 pointer-events-none px-3 py-2 rounded-lg text-sm shadow-lg"
          style={{
            left: `${(x(hp.t) / W) * 100}%`,
            transform: hover > points.length / 2 ? 'translateX(calc(-100% - 12px))' : 'translateX(12px)',
            background: '#1a1a19',
            border: '1px solid rgba(255,255,255,0.10)',
          }}
        >
          <p className="mb-1" style={{ color: INK.muted }}>{new Date(hp.t * 1000).toLocaleTimeString('fr-FR')}</p>
          {SERIES.map((s) => (
            <p key={s.key} className="flex items-center gap-2 whitespace-nowrap">
              <span className="inline-block w-3 h-0.5 rounded" style={{ background: s.color }} />
              <strong style={{ color: INK.primary }}>{fmt(hp[s.key])}</strong>
              <span style={{ color: INK.secondary }}>{s.label}</span>
            </p>
          ))}
        </div>
      )}

      {/* Vue tableau : les valeurs restent accessibles sans survol */}
      <details className="mt-3 text-sm" style={{ color: INK.secondary }}>
        <summary className="cursor-pointer">Voir les données</summary>
        <div className="max-h-48 mt-2 overflow-y-auto">
          <table className="w-full text-left" style={{ fontVariantNumeric: 'tabular-nums' }}>
            <thead style={{ color: INK.muted }}>
              <tr><th className="pr-4">Heure</th><th className="pr-4">Requêtes/s</th><th>Erreurs/s</th></tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.t}><td className="pr-4">{new Date(p.t * 1000).toLocaleTimeString('fr-FR')}</td><td className="pr-4">{fmt(p.total)}</td><td>{fmt(p.errors)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

export default TrafficChart
