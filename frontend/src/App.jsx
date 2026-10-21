import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import FormulaireConnexion from './components/FormulaireConnexion'
import FormulaireInscription from './components/FormulaireInscription'
import Dashboard from './components/Dashboard'
import fond from './assets/phenixBackground.png'

function App() {
  // Token JWT gardé en mémoire uniquement : perdu au rechargement
  const [token, setToken] = useState(null)

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
              token ? (
                <p className="text-2xl font-bold text-white drop-shadow">Connecté</p>
              ) : (
                <FormulaireConnexion onLogin={setToken} />
              )
            }
          />
          <Route path="/inscription" element={<FormulaireInscription />} />
          <Route path="/dashboard" element={token ? <Dashboard token={token} /> : <Navigate to="/" />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
