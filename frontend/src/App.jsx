import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import FormulaireConnexion from './components/FormulaireConnexion'
import FormulaireInscription from './components/FormulaireInscription'
import Dashboard from './components/Dashboard'
import fond from './assets/phenixBackground.png'

function App() {
  // Token JWT gardé en mémoire uniquement : perdu au rechargement
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)

  // Après le login : on garde le token, puis on demande au backend qui est connecté (dont son rôle)
  async function handleLogin(newToken) {
    setToken(newToken)

    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${newToken}` },
    })
    if (!res.ok) {
      setToken(null)
      return
    }
    setUser(await res.json())
  }

  return (
    <BrowserRouter>
      <main
        className="min-h-screen flex items-center justify-center bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: `url(${fond})` }}
      >
        <Routes>
          <Route
            path="/"
            element={
              !user ? (
                <FormulaireConnexion onLogin={handleLogin} />
              ) : user.role === 'ADMIN' ? (
                <Navigate to="/dashboard" />
              ) : (
                <p className="text-2xl font-bold text-white drop-shadow">Connecté</p>
              )
            }
          />
          <Route path="/inscription" element={<FormulaireInscription />} />
          {/* Réservé aux ADMIN ; user?.role évite une erreur quand user vaut null */}
          <Route
            path="/dashboard"
            element={user?.role === 'ADMIN' ? <Dashboard token={token} /> : <Navigate to="/" />}
          />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
