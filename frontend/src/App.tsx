import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import Home from './pages/Home'
import Performance from './pages/Performance'
import Position from './pages/Position'
import FiatDeposits from './pages/FiatDeposits'
import Layout from './components/common/Layout'

function PositionsEmpty() {
  return (
    <div className="panel text-center py-12 px-4">
      <div className="lbl mb-2">§2 · Positions</div>
      <div className="page-title mt-0">No positions yet</div>
      <p className="cap mt-3 max-w-md mx-auto leading-relaxed">
        Synced holdings will appear here. Connect an exchange or wallet, then open a position from
        Overview.
      </p>
      <Link
        to="/"
        className="inline-block mt-6 font-mono text-xs text-sillage-soft hover:text-sillage-ink no-underline"
      >
        ← back to overview
      </Link>
    </div>
  )
}

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/fiat-deposits" element={<FiatDeposits />} />
          <Route path="/position" element={<PositionsEmpty />} />
          <Route path="/position/:id" element={<Position />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App

