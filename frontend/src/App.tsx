import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Performance from './pages/Performance'
import Position from './pages/Position'
import Asset from './pages/Asset'
import FiatDeposits from './pages/FiatDeposits'
import Settings from './pages/Settings'
import Layout from './components/common/Layout'

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/fiat-deposits" element={<FiatDeposits />} />
          <Route path="/asset/:symbol" element={<Asset />} />
          <Route path="/position/:id" element={<Position />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App
