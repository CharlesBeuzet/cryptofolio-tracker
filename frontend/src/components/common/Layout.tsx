import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-crypto-bg">
      <nav className="border-b border-crypto-border bg-crypto-card">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <Link
                to="/"
                className="flex items-center px-4 text-xl font-bold text-crypto-green"
              >
                ₿ CryptoFolio
              </Link>
              <div className="flex space-x-4 ml-8">
                <Link
                  to="/"
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                    location.pathname === '/'
                      ? 'bg-crypto-border text-crypto-green'
                      : 'text-gray-300 hover:bg-crypto-border hover:text-white'
                  }`}
                >
                  Home
                </Link>
                <Link
                  to="/performance"
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                    location.pathname === '/performance'
                      ? 'bg-crypto-border text-crypto-green'
                      : 'text-gray-300 hover:bg-crypto-border hover:text-white'
                  }`}
                >
                  Performance
                </Link>
                <Link
                  to="/fiat-deposits"
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                    location.pathname === '/fiat-deposits'
                      ? 'bg-crypto-border text-crypto-green'
                      : 'text-gray-300 hover:bg-crypto-border hover:text-white'
                  }`}
                >
                  Fiat deposits
                </Link>
              </div>
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}

