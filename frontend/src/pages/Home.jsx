import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowRight } from 'lucide-react';

export default function Home() {
  const [topic, setTopic] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [contextUrls, setContextUrls] = useState([]);
  const [showSources, setShowSources] = useState(false);
  const navigate = useNavigate();

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!topic) return;
    setIsSearching(true);
    setContextUrls([]);
    setShowSources(false);

    try {
      // Step 1: Fast web search
      const searchRes = await fetch("http://localhost:8000/api/schema/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic })
      });
      const searchData = await searchRes.json();
      setContextUrls(searchData.context_urls);
      setIsSearching(false);
      setIsGenerating(true);

      // Step 2: Slow schema generation
      const response = await fetch("http://localhost:8000/api/schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, context_text: searchData.context_text })
      });
      const data = await response.json();
      navigate('/schema', { state: { topic, initialColumns: data.columns, contextUrls: searchData.context_urls } });
    } catch (e) {
      console.error(e);
      setIsSearching(false);
      setIsGenerating(false);
    }
  };

  return (
    <div className="animate-fade-in-up" style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center', position: 'relative', zIndex: 1 }}>
      <h2 style={{ fontSize: '2rem', marginBottom: '1rem' }}>What do you want to research?</h2>
      <p className="text-secondary" style={{ marginBottom: '2rem' }}>
        Enter a topic. Autonomous agents will build a schema, discover sources, and extract a structured dataset, ready to export.
      </p>

      <form onSubmit={handleGenerate} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'stretch' }}>
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. Y Combinator AI Startups 2024"
          style={{
            background: 'var(--color-ink)',
            border: '1px solid var(--color-line)',
            color: 'var(--color-text-primary)',
            padding: '1rem',
            fontSize: '1.25rem',
            borderRadius: '4px',
            fontFamily: 'var(--font-body)',
            width: '100%',
            outline: 'none'
          }}
          disabled={isGenerating}
        />
        <button
          type="submit"
          disabled={isGenerating || isSearching || !topic}
          style={{
            background: (isGenerating || isSearching) ? 'var(--color-line)' : 'var(--color-status-resolved)',
            color: (isGenerating || isSearching) ? 'var(--color-text-secondary)' : '#111',
            border: 'none',
            padding: '1rem',
            cursor: (isGenerating || isSearching) || !topic ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
            fontFamily: 'var(--font-mono)',
            fontSize: '1rem',
            fontWeight: 600,
            borderRadius: '4px'
          }}>
          {isSearching ? 'Searching Web...' : isGenerating ? 'Generating Schema...' : <><Sparkles size={18} /> Generate Schema <ArrowRight size={18} /></>}
        </button>

        {/* Sources Accordion */}
        {(isGenerating || contextUrls.length > 0) && (
          <div style={{ marginTop: '1rem', textAlign: 'left' }}>
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
                padding: 0
              }}
            >
              {showSources ? '▼ Hide Sources' : '▶ View Sources Being Analyzed'}
            </button>

            {showSources && (
              <div className="card" style={{ marginTop: '0.5rem', padding: '1rem', background: 'var(--color-ink)', fontSize: '0.85rem' }}>
                {contextUrls.length > 0 ? (
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--color-text-muted)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    {contextUrls.map((url, i) => (
                      <li key={i}>
                        <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-text-muted)', textDecoration: 'underline' }}>{url}</a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-muted">No sources found. Using fallback LLM knowledge.</span>
                )}
              </div>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
