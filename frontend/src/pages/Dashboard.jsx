import { useEffect, useState, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Activity, StopCircle, PauseCircle, PlayCircle, Database, CheckCircle, Table, BarChart2, Zap, Download, Key, AlertTriangle, X } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

// ---------------------------------------------------------------------------
// ApiKeyModal
// ---------------------------------------------------------------------------
function ApiKeyModal({ runId, onKeySubmitted, onDismiss }) {
  const [keyInput, setKeyInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    const trimmed = keyInput.trim();
    if (!trimmed) { setError('Please enter a valid API key.'); return; }
    setSubmitting(true);
    setError('');
    try {
      const res = await fetch('http://localhost:8000/api/set_api_key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, api_key: trimmed }),
      });
      const data = await res.json();
      if (data.error) { setError(data.error); setSubmitting(false); return; }
      onKeySubmitted();
    } catch (e) {
      setError('Failed to send key — is the server running?');
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--color-panel)',
        border: '1px solid rgba(239,68,68,0.4)',
        borderRadius: '12px',
        padding: '2rem',
        maxWidth: '480px', width: '90%',
        boxShadow: '0 0 60px rgba(239,68,68,0.15), 0 24px 48px rgba(0,0,0,0.5)',
        animation: 'fadeInUp 0.3s ease',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%',
            background: 'rgba(239,68,68,0.15)',
            border: '1px solid rgba(239,68,68,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertTriangle size={20} color="#ef4444" />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--color-text)' }}>API Limit Reached</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>Hugging Face quota exhausted</p>
          </div>
          <button onClick={onDismiss} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
          The owner's Hugging Face API key has been exhausted. You can provide your own key to
          continue — it will <strong style={{ color: 'var(--color-text)' }}>only be used for this session</strong> and is
          never stored.
        </p>

        {/* Input */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '0.4rem', fontFamily: 'var(--font-mono)' }}>
            <Key size={12} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
            Your Hugging Face API Key
          </label>
          <input
            type="password"
            value={keyInput}
            onChange={e => { setKeyInput(e.target.value); setError(''); }}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            placeholder="hf_xxxxxxxxxxxxxxxxxxxxxxxx"
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--color-ink)',
              border: `1px solid ${error ? '#ef4444' : 'var(--color-line)'}`,
              borderRadius: '6px', padding: '0.65rem 0.85rem',
              color: 'var(--color-text)', fontSize: '0.9rem',
              fontFamily: 'var(--font-mono)', outline: 'none',
            }}
          />
          {error && <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#ef4444', fontFamily: 'var(--font-mono)' }}>{error}</p>}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <button onClick={onDismiss} style={{
            background: 'transparent', border: '1px solid var(--color-line)',
            color: 'var(--color-text-secondary)', padding: '0.6rem 1.1rem',
            borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem',
          }}>
            Export what I have
          </button>
          <button onClick={handleSubmit} disabled={submitting} style={{
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            border: 'none', color: '#fff',
            padding: '0.6rem 1.25rem', borderRadius: '6px',
            cursor: submitting ? 'wait' : 'pointer',
            fontWeight: 600, fontSize: '0.875rem',
            opacity: submitting ? 0.7 : 1,
            display: 'flex', alignItems: 'center', gap: '0.5rem',
          }}>
            <Key size={14} />{submitting ? 'Connecting...' : 'Continue Extraction'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const runId = location.state?.runId;
  const topic = location.state?.topic || "Unknown Topic";
  const schemaColumns = location.state?.columns || [];
  
  const [logs, setLogs] = useState([]);
  const [dataRows, setDataRows] = useState([]);
  const [isRunning, setIsRunning] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [activeTab, setActiveTab] = useState('analytics');
  const [agentStatus, setAgentStatus] = useState("Initializing Pipeline...");
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [isPartialExport, setIsPartialExport] = useState(false);

  // Stream Logs & Agent Status
  useEffect(() => {
    if (!runId) return;
    const evtSource = new EventSource(`http://localhost:8000/api/stream?run_id=${runId}`);
    evtSource.addEventListener("log", (e) => {
      const data = JSON.parse(e.data);
      setLogs((prev) => {
        if (prev.some(l => l.log_id === data.log_id)) return prev;
        return [...prev, data];
      });
      
      // API key exhausted mid-run
      if (data.stage === 'api_key_exhausted') {
        setShowApiKeyModal(true);
        setAgentStatus('⚠️ API limit reached — waiting for user key...');
        return;
      }

      if (data.outcome === 'cancelled' || data.outcome === 'completed' || data.outcome === 'completed_partial') {
        setIsRunning(false);
        setIsStopping(false);
        setShowApiKeyModal(false);
        if (data.outcome === 'cancelled') {
          setAgentStatus('Extraction Stopped by User.');
        } else if (data.outcome === 'completed_partial') {
          setIsPartialExport(true);
          setAgentStatus('Extraction paused — partial dataset ready for export.');
        } else {
          setAgentStatus('Extraction Completed!');
        }
        return;
      }

      if (!isPaused) {
        if (data.stage === 'source_agent_start') setAgentStatus("Checking Database & Generating Search Queries...");
        if (data.stage === 'source_agent_end') setAgentStatus("Sources discovered. Booting Research Agent...");
        if (data.stage === 'research_agent_start' && data.outcome.startsWith('processing_')) {
           setAgentStatus(`Reading & Extracting: ${data.outcome.replace('processing_', '')}`);
        }
        if (data.stage === 'research_agent_end') setAgentStatus("Pipeline Completed. Ready for export.");
        
        if (data.stage === 'completion_agent_start') setAgentStatus("Scanning dataset for missing values...");
        if (data.stage === 'completion_agent_search') setAgentStatus(`Completing missing fields for: ${data.outcome.replace('completing_', '')}`);
        if (data.stage === 'completion_agent_end') setAgentStatus("Completion Agent Finished. Ready for export.");
      }
    });
    return () => evtSource.close();
  }, [runId, isPaused]);

  // Poll Data
  useEffect(() => {
    if (!runId) return;
    
    const fetchData = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/run/${runId}/data`);
        const json = await res.json();
        setDataRows(json.data || []);
      } catch (err) {
        console.error("Failed to fetch data:", err);
      }
    };

    // Fetch immediately once
    fetchData();

    // Then poll if running
    if (!isRunning) return;
    
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, [runId, isRunning]);

  const findMoreData = async () => {
    setIsRunning(true);
    setAgentStatus("Finding more sources...");
    try {
      const res = await fetch("http://127.0.0.1:8000/api/find_more_sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId, topic: topic, columns: schemaColumns })
      });
      const data = await res.json();
      if (data.error) {
        console.error(data.error);
        setIsRunning(false);
      }
    } catch (e) {
      console.error(e);
      setIsRunning(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await fetch(`http://localhost:8000/api/stop_extraction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId })
      });
    } catch (err) {
      console.error(err);
      setIsStopping(false);
    }
  };

  const handlePauseToggle = async () => {
    try {
      if (isPaused) {
        setIsPaused(false);
        setAgentStatus("Resuming Extraction...");
        await fetch(`http://localhost:8000/api/resume_extraction`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId })
        });
      } else {
        setIsPaused(true);
        setAgentStatus("⏸️ Agent Paused");
        await fetch(`http://localhost:8000/api/pause_extraction`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId })
        });
      }
    } catch (err) {
      console.error("Error toggling pause", err);
    }
  };

  const exportCSV = () => {
    if (dataRows.length === 0) return;
    
    // Get headers
    const headers = ["source_url", ...columns];
    
    // Convert to CSV string
    const csvContent = [
      headers.join(","),
      ...dataRows.map(row => 
        headers.map(h => {
          let val = row[h];
          if (val === null || val === 'NULL' || val === undefined) val = "";
          // Escape quotes and commas
          val = String(val).replace(/"/g, '""');
          return `"${val}"`;
        }).join(",")
      )
    ].join("\n");
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `${topic.replace(/\s+/g, '_')}_dataset.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Extract columns
  const columns = useMemo(() => {
    if (dataRows.length === 0) return [];
    const keys = new Set();
    dataRows.forEach(row => {
      Object.keys(row).forEach(k => {
        if (k !== 'id' && k !== 'source_url') keys.add(k);
      });
    });
    return Array.from(keys);
  }, [dataRows]);

  // Compute Analytics
  const analytics = useMemo(() => {
    const totalRows = dataRows.length;
    let totalFields = 0;
    let nullFields = 0;
    const sourceCounts = {};
    const nullsPerColumn = {};

    columns.forEach(col => nullsPerColumn[col] = 0);

    dataRows.forEach(row => {
      const src = row.source_url || "Unknown";
      sourceCounts[src] = (sourceCounts[src] || 0) + 1;
      
      Object.keys(row).forEach(k => {
        if (k !== 'id' && k !== 'source_url') {
          totalFields++;
          const isNull = (row[k] === null || row[k] === "NULL" || row[k] === "");
          if (isNull) {
            nullFields++;
            if (nullsPerColumn[k] !== undefined) {
              nullsPerColumn[k]++;
            }
          }
        }
      });
    });

    const dataQuality = totalFields > 0 ? (((totalFields - nullFields) / totalFields) * 100).toFixed(1) : 100;
    
    const getHostname = (urlStr) => {
      try {
        return new URL(urlStr).hostname.replace('www.', '');
      } catch (e) {
        return urlStr || "Unknown";
      }
    };

    const pieData = Object.keys(sourceCounts).map(src => ({
      name: getHostname(src),
      value: sourceCounts[src],
      fullName: src
    }));

    const barData = Object.keys(nullsPerColumn).map(col => ({
      column: col,
      missing: nullsPerColumn[col]
    }));

    return { totalRows, totalFields, nullFields, dataQuality, pieData, barData };
  }, [dataRows, columns]);


  if (!runId) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center' }}>
        <h2>No Active Extraction</h2>
        <button onClick={() => navigate('/')} className="card" style={{ cursor: 'pointer', marginTop: '1rem', background: 'var(--color-ink)' }}>Go Home</button>
      </div>
    );
  }

  return (
    <div style={{ padding: '0 2rem', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 'calc(100vh - 80px)' }}>
      {/* API Key Modal */}
      {showApiKeyModal && (
        <ApiKeyModal
          runId={runId}
          onKeySubmitted={() => {
            setShowApiKeyModal(false);
            setIsRunning(true);
            setAgentStatus('🔑 Key accepted — resuming extraction...');
          }}
          onDismiss={() => {
            setShowApiKeyModal(false);
            setIsRunning(false);
            setIsPartialExport(true);
            setAgentStatus('Extraction paused — partial dataset ready for export.');
          }}
        />
      )}
      {/* Header & Agent Status Monitor */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem', alignItems: 'flex-start' }}>
        <div>
          {isRunning ? (
            <h2 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={24} color={isPaused ? "#f59e0b" : "var(--color-status-researching)"} />
              Workspace: <span className="text-primary">{topic}</span>
            </h2>
          ) : (
            <h2 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-status-resolved)' }}>
              <CheckCircle size={24} />
              Final Dataset Report: <span className="text-primary">{topic}</span>
            </h2>
          )}
          
          {/* Agent Transparency Banner */}
          {isRunning && (
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '0.75rem', 
              background: 'var(--color-ink)', padding: '0.5rem 1rem', 
              borderRadius: '4px', border: '1px solid var(--color-line)',
              fontFamily: 'var(--font-mono)', fontSize: '0.85rem'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div className={isPaused ? "" : "pulse-dot"} style={{ width: '8px', height: '8px', background: isPaused ? '#f59e0b' : 'var(--color-status-researching)', borderRadius: '50%' }}></div>
                    <span style={{ color: 'var(--color-text-secondary)' }}>🤖 Agent Status:</span>
                    <span style={{ color: isPaused ? '#f59e0b' : 'var(--color-primary)', maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {agentStatus}
                    </span>
                </div>
            </div>
          )}
        </div>
        
        {isRunning ? (
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button onClick={handlePauseToggle} style={{
              background: 'rgba(245, 158, 11, 0.1)',
              color: '#f59e0b',
              border: '1px solid #f59e0b',
              padding: '0.75rem 1.5rem',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              cursor: 'pointer',
              fontWeight: 600
            }}>
              {isPaused ? <><PlayCircle size={18} /> Resume</> : <><PauseCircle size={18} /> Pause</>}
            </button>
            <button onClick={handleStop} disabled={isStopping} style={{
              background: 'rgba(239, 68, 68, 0.1)',
              color: '#ef4444',
              border: '1px solid #ef4444',
              padding: '0.75rem 1.5rem',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              cursor: isStopping ? 'wait' : 'pointer',
              fontWeight: 600
            }}>
              <StopCircle size={18} /> {isStopping ? 'Stopping...' : 'Stop Extraction'}
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '1rem' }}>
            {dataRows.length > 0 && !isPartialExport && (
              <button onClick={findMoreData} disabled={isRunning} style={{ 
                background: 'rgba(59, 130, 246, 0.1)', 
                color: '#3b82f6', 
                border: '1px solid #3b82f6', 
                padding: '0.75rem 1.5rem', 
                borderRadius: '4px', 
                cursor: isRunning ? 'wait' : 'pointer', 
                fontWeight: 600 
              }}>
                Find More Sources
              </button>
            )}
            <button onClick={exportCSV} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Download size={18} /> {isPartialExport ? 'Export Partial Dataset (CSV)' : 'Export Dataset (CSV)'}
            </button>
          </div>
        )}

      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--color-line)', marginBottom: '2rem' }}>
        <button 
          onClick={() => setActiveTab('analytics')}
          style={{ 
            background: 'transparent', 
            border: 'none', 
            borderBottom: activeTab === 'analytics' ? '2px solid var(--color-primary)' : '2px solid transparent',
            color: activeTab === 'analytics' ? 'var(--color-text)' : 'var(--color-text-secondary)',
            padding: '0.5rem 1rem', 
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            fontWeight: activeTab === 'analytics' ? 'bold' : 'normal',
            transition: 'all 0.2s'
          }}>
          <BarChart2 size={16} /> Analytics Dashboard
        </button>
        <button 
          onClick={() => setActiveTab('data')}
          style={{ 
            background: 'transparent', 
            border: 'none', 
            borderBottom: activeTab === 'data' ? '2px solid var(--color-primary)' : '2px solid transparent',
            color: activeTab === 'data' ? 'var(--color-text)' : 'var(--color-text-secondary)',
            padding: '0.5rem 1rem', 
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            fontWeight: activeTab === 'data' ? 'bold' : 'normal',
            transition: 'all 0.2s'
          }}>
          <Table size={16} /> Data View <span className="badge" style={{ marginLeft: '0.25rem', background: 'var(--color-ink)' }}>{analytics.totalRows}</span>
        </button>
      </div>

      {/* Tab Content */}
      <div style={{ flex: 1 }}>
        {activeTab === 'analytics' && (
          <div className="animate-fade-in-up">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="text-muted font-mono" style={{ fontSize: '0.75rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Database size={14} /> EXTRACTED ROWS
                    </div>
                    <div className="font-mono" style={{ fontSize: '3rem', color: 'var(--color-text)' }}>{analytics.totalRows}</div>
                </div>
                <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="text-muted font-mono" style={{ fontSize: '0.75rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Zap size={14} /> OVERALL DATA HEALTH
                    </div>
                    <div className="font-mono" style={{ fontSize: '3rem', color: analytics.dataQuality > 80 ? 'var(--color-status-resolved)' : (analytics.dataQuality > 50 ? '#f59e0b' : 'var(--color-status-failed)') }}>
                        {analytics.dataQuality}%
                    </div>
                </div>
                <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="text-muted font-mono" style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}>TOTAL NULL FIELDS</div>
                    <div className="font-mono" style={{ fontSize: '3rem', color: analytics.nullFields > 0 ? '#f59e0b' : 'var(--color-status-resolved)' }}>
                        {analytics.nullFields}
                    </div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                {/* Column Sparsity Bar Chart */}
                <div className="card" style={{ height: '350px', display: 'flex', flexDirection: 'column' }}>
                    <h3 style={{ fontSize: '1rem', marginBottom: '1rem', color: 'var(--color-text)' }}>Column Sparsity (Missing Data)</h3>
                    {analytics.barData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={analytics.barData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" vertical={false} />
                                <XAxis dataKey="column" stroke="var(--color-text-muted)" tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }} angle={-45} textAnchor="end" height={60} />
                                <YAxis stroke="var(--color-text-muted)" tick={{ fontSize: 10 }} allowDecimals={false} />
                                <RechartsTooltip 
                                    contentStyle={{ backgroundColor: 'var(--color-panel)', borderColor: 'var(--color-line)', borderRadius: '4px' }}
                                    itemStyle={{ fontFamily: 'var(--font-mono)' }}
                                    formatter={(value) => [`${value} Nulls`, "Missing"]}
                                />
                                <Bar dataKey="missing" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>Waiting for data...</div>
                    )}
                </div>

                {/* Source Contribution Pie Chart */}
                <div className="card" style={{ height: '350px', display: 'flex', flexDirection: 'column' }}>
                    <h3 style={{ fontSize: '1rem', marginBottom: '1rem' }}>Source Contribution (Rows)</h3>
                    {analytics.pieData.length > 0 ? (
                        <div style={{ flex: 1, minHeight: 0 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                            <Pie
                                data={analytics.pieData}
                                cx="50%"
                                cy="50%"
                                innerRadius={70}
                                outerRadius={110}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {analytics.pieData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <RechartsTooltip 
                                contentStyle={{ backgroundColor: 'var(--color-panel)', borderColor: 'var(--color-line)', borderRadius: '4px' }}
                                itemStyle={{ fontFamily: 'var(--font-mono)' }}
                            />
                            <Legend verticalAlign="bottom" align="center" wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginTop: '10px' }} />
                            </PieChart>
                        </ResponsiveContainer>
                        </div>
                    ) : (
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>Waiting for data...</div>
                    )}
                </div>
            </div>
          </div>
        )}

        {activeTab === 'data' && (
            <div className="animate-fade-in-up card" style={{ height: 'calc(100vh - 280px)', overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: 0 }}>
                {dataRows.length > 0 ? (
                <div style={{ overflow: 'auto', flex: 1 }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '0.85rem', textAlign: 'left' }}>
                    <thead style={{ position: 'sticky', top: 0, background: 'var(--color-panel)', zIndex: 1 }}>
                        <tr>
                        <th style={{ padding: '1rem', color: 'var(--color-text-secondary)', fontWeight: '600', borderBottom: '1px solid var(--color-line)' }}>Source</th>
                        {columns.map(col => (
                            <th key={col} style={{ padding: '1rem', color: 'var(--color-text-secondary)', fontWeight: '600', borderBottom: '1px solid var(--color-line)' }}>{col}</th>
                        ))}
                        </tr>
                    </thead>
                    <tbody>
                        {dataRows.slice().reverse().map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--color-bg)', transition: 'background 0.2s', ':hover': { background: 'var(--color-ink)' } }}>
                            <td style={{ padding: '1rem', color: 'var(--color-primary)', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row.source_url}>
                            <a href={row.source_url !== "Unknown" ? row.source_url : "#"} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none' }}>
                                {(() => {
                                    try {
                                        return new URL(row.source_url).hostname.replace('www.', '');
                                    } catch(e) {
                                        return row.source_url || "Unknown";
                                    }
                                })()}
                            </a>
                            </td>
                            {columns.map(col => (
                            <td key={col} style={{ padding: '1rem', color: (row[col] === null || row[col] === 'NULL') ? 'var(--color-text-muted)' : 'var(--color-text)' }}>
                                {(row[col] === null || row[col] === 'NULL') ? <i>NULL</i> : String(row[col])}
                            </td>
                            ))}
                        </tr>
                        ))}
                    </tbody>
                    </table>
                </div>
                ) : (
                <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
                    No rows extracted yet. Ensure the Research Agent has found a source and is currently reading it...
                </div>
                )}
            </div>
        )}
      </div>
    </div>
  );
}
