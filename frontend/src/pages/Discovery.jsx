import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Play } from 'lucide-react';

export default function Discovery() {
  const location = useLocation();
  const navigate = useNavigate();
  const topic = location.state?.topic || "Custom Dataset";
  
  const initialCandidates = location.state?.initialCandidates || [];
  const columns = location.state?.columns || [];
  const [candidates, setCandidates] = useState(initialCandidates);

  const toggleCheck = (id) => {
    setCandidates(prev => prev.map(c => c.id === id ? { ...c, checked: !c.checked } : c));
  };

  const handleStart = async () => {
    const selectedEntities = candidates.filter(c => c.checked).map(c => c.url);
    try {
        const response = await fetch("http://localhost:8000/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic, entities: selectedEntities, schema_def: columns })
        });
        const data = await response.json();
        navigate('/dashboard', { state: { runId: data.run_id } });
    } catch (e) {
        console.error(e);
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '2rem auto' }}>
      <div style={{ marginBottom: '2rem' }}>
        <div className="text-muted font-mono" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>STEP 2 / 2</div>
        <h2>Entity Discovery Review</h2>
        <p className="text-secondary">The discovery agent found {candidates.length} candidates for <strong className="text-primary">"{topic}"</strong>. Prune the list before starting research.</p>
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '2rem' }}>
        {candidates.map(candidate => (
          <div key={candidate.id} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '0.5rem 0', borderBottom: '1px solid var(--color-line)' }}>
            <input 
              type="checkbox" 
              checked={candidate.checked} 
              onChange={() => toggleCheck(candidate.id)} 
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', opacity: candidate.checked ? 1 : 0.5 }}>
              <span style={{ textDecoration: candidate.checked ? 'none' : 'line-through', color: 'var(--color-text-primary)', fontWeight: 500 }}>
                {candidate.url}
              </span>
              <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: '0.25rem' }}>
                {candidate.metadata_draft || "No description available"}
              </span>
            </div>
            <span className="badge" style={{ background: 'var(--color-line)', color: 'var(--color-text-secondary)' }}>{candidate.source_type}</span>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="text-muted font-mono">
          {candidates.filter(c => c.checked).length} entities selected for research
        </div>
        <button 
          onClick={handleStart}
          style={{ 
            background: 'var(--color-status-resolved)', 
            color: '#111', 
            border: 'none',
            padding: '0.75rem 1.5rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            borderRadius: '4px'
          }}>
          <Play size={16} /> Start Pipeline
        </button>
      </div>
    </div>
  );
}
