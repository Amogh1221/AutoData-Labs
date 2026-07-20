import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, Trash2, Plus, Loader2, AlertCircle } from 'lucide-react';

export default function SchemaBuilder() {
  const location = useLocation();
  const navigate = useNavigate();
  const topic = location.state?.topic || "Custom Dataset";
  
  const initialColumns = (location.state?.initialColumns || []).map((col, index) => ({
    ...col,
    required: index === 0
  }));
  const contextUrls = location.state?.contextUrls || [];
  const [columns, setColumns] = useState(initialColumns);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const [isAddingColumn, setIsAddingColumn] = useState(false);
  const [newColumnName, setNewColumnName] = useState("");
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState("");

  const handleDelete = (id) => {
    setColumns(prev => prev.filter(c => c.id !== id));
  }

  const toggleRequired = (id) => {
    setColumns(prev => prev.map(c => c.id === id ? { ...c, required: !c.required } : c));
  }

  const handleAddColumnSubmit = async (e) => {
    e.preventDefault();
    if (!newColumnName.trim()) return;
    
    setIsValidating(true);
    setValidationError("");
    
    try {
        const response = await fetch("http://localhost:8000/api/schema/validate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                topic,
                current_schema: columns,
                new_column_name: newColumnName.trim()
            })
        });
        const data = await response.json();
        
        if (data.valid) {
            setColumns(prev => [...prev, {
                id: Date.now(),
                name: newColumnName.trim().toLowerCase().replace(/\s+/g, '_'),
                type: "string",
                reason: data.reason || "User requested column",
                required: false
            }]);
            setIsAddingColumn(false);
            setNewColumnName("");
        } else {
            setValidationError(data.reason);
        }
    } catch (e) {
        setValidationError("Failed to validate column. Please try again.");
    } finally {
        setIsValidating(false);
    }
  };

  const handleContinue = async () => {
    if (!columns.some(c => c.required)) {
        setValidationError("You must mark at least one field as 'Required'. This field is used as the Primary Key to prevent duplicate data in your dataset.");
        return;
    }
    
    setIsDiscovering(true);
    setValidationError(null);
    try {
        const response = await fetch("http://localhost:8000/api/start_extraction", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic, columns })
        });
        const data = await response.json();
        navigate('/dashboard', { state: { runId: data.run_id, topic, columns } });
    } catch (e) {
        console.error(e);
        setIsDiscovering(false);
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '2rem auto' }}>
      <div style={{ marginBottom: '2rem' }}>
        <div className="text-muted font-mono" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>STEP 1 / 2</div>
        <h2>Schema Approval</h2>
        <p className="text-secondary">The planner agent proposed these extraction fields based on: <strong className="text-primary">"{topic}"</strong></p>
      </div>

      {contextUrls.length > 0 && (
        <div className="card" style={{ marginBottom: '2rem', padding: '1rem', background: 'var(--color-ink)' }}>
          <button
              type="button"
              onClick={() => setShowSources(!showSources)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-text-secondary)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: 0,
                fontWeight: 600
              }}
            >
              {showSources ? '▼ Hide Sources analyzed by AI to generate this schema' : '▶ View Sources analyzed by AI to generate this schema'}
          </button>
          {showSources && (
            <ul style={{ marginTop: '0.5rem', marginBottom: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: 'var(--color-text-muted)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {contextUrls.map((url, i) => (
                <li key={i}>
                  <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-text-muted)', textDecoration: 'underline' }}>{url}</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2rem' }}>
        {columns.map(col => (
          <div key={col.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem' }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                <strong className="font-mono">{col.name}</strong>
                <span className="badge" style={{ background: 'var(--color-line)', color: 'var(--color-text-secondary)' }}>{col.type}</span>
              </div>
              <div className="text-muted" style={{ fontSize: '0.85rem' }}>{col.reason}</div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.85rem', color: col.required ? 'var(--color-primary)' : 'var(--color-text-secondary)', fontWeight: col.required ? '600' : 'normal' }}>
              <input 
                type="checkbox" 
                checked={col.required || false} 
                onChange={() => toggleRequired(col.id)} 
                style={{ cursor: 'pointer', accentColor: 'var(--color-primary)' }}
              />
              Required
            </label>
            <button onClick={() => handleDelete(col.id)} style={{ background: 'transparent', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', marginLeft: '1rem' }}>
              <Trash2 size={18} />
            </button>
          </div>
        ))}
        
        {!isAddingColumn ? (
          <button onClick={() => setIsAddingColumn(true)} className="card" style={{ 
            borderStyle: 'dashed', 
            cursor: 'pointer', 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            gap: '0.5rem',
            color: 'var(--color-text-secondary)',
            background: 'transparent'
          }}>
            <Plus size={16} /> Add Custom Column
          </button>
        ) : (
          <form onSubmit={handleAddColumnSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', border: '1px solid var(--color-primary)' }}>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <input 
                type="text" 
                value={newColumnName}
                onChange={e => setNewColumnName(e.target.value)}
                placeholder="e.g. founder_linkedin"
                style={{ flex: 1, padding: '0.75rem', background: 'var(--color-bg)', border: '1px solid var(--color-line)', color: 'var(--color-text)', borderRadius: '4px' }}
                disabled={isValidating}
                autoFocus
              />
              <button 
                type="submit"
                disabled={isValidating || !newColumnName.trim()}
                style={{ 
                  background: 'var(--color-primary)', 
                  color: '#FFF', 
                  border: 'none',
                  padding: '0 1.5rem',
                  cursor: isValidating ? 'not-allowed' : 'pointer',
                  borderRadius: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem'
                }}>
                {isValidating ? <Loader2 size={16} className="spin" /> : 'Validate & Add'}
              </button>
              <button 
                type="button"
                onClick={() => { setIsAddingColumn(false); setValidationError(""); setNewColumnName(""); }}
                disabled={isValidating}
                style={{ background: 'transparent', border: '1px solid var(--color-line)', color: 'var(--color-text)', padding: '0 1rem', borderRadius: '4px', cursor: 'pointer' }}>
                Cancel
              </button>
            </div>
            
            {validationError && (
              <div style={{ display: 'flex', gap: '0.5rem', padding: '0.75rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '4px', color: '#ef4444' }}>
                <AlertCircle size={18} style={{ flexShrink: 0 }} />
                <div style={{ fontSize: '0.9rem' }}>
                  <strong>Planner Agent Rejected Column:</strong><br />
                  {validationError}
                </div>
              </div>
            )}
          </form>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button 
          onClick={handleContinue}
          disabled={isDiscovering}
          style={{ 
            background: 'var(--color-status-researching)', 
            color: '#FFF', 
            border: 'none',
            padding: '0.75rem 1.5rem',
            cursor: isDiscovering ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            borderRadius: '4px'
          }}>
          {isDiscovering ? 'Starting Live Extraction...' : 'Approve & Start Live Extraction'} <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
