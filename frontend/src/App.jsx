import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Home from './pages/Home';
import SchemaBuilder from './pages/SchemaBuilder';
import Dashboard from './pages/Dashboard';
import './index.css';

export default function App() {
  return (
    <BrowserRouter>
      <div className="graph-bg" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* Global Navigation Bar */}
        <header style={{ 
          borderBottom: '1px solid var(--color-line)', 
          background: 'var(--color-ink)',
          padding: '1rem 2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            <h1 style={{ fontSize: '1.25rem', margin: 0 }}>AutoData Labs</h1>
          </Link>
          <div className="font-mono text-muted" style={{ fontSize: '0.85rem' }}>
            Agentic Execution Pipeline
          </div>
        </header>

        {/* Page Content */}
        <div style={{ flex: 1, padding: '2rem' }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/schema" element={<SchemaBuilder />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}
