import React, { useState, useRef, useEffect } from 'react';
import { Database, RefreshCw, Terminal } from 'lucide-react';

export default function SyncPanel({ 
  defaultConfluenceId = '100', 
  defaultGithubOrg = 'mock-org',
  lastConfluenceSync = 'Never',
  lastGithubSync = 'Never',
  onSyncSuccess
}) {
  const [confluenceId, setConfluenceId] = useState(defaultConfluenceId);
  const [githubOrg, setGithubOrg] = useState(defaultGithubOrg);
  const [syncingType, setSyncingType] = useState(null); // 'confluence', 'github', or null
  const [logs, setLogs] = useState([]);
  
  const logEndRef = useRef(null);

  // Sync inputs with defaults loaded from server
  useEffect(() => {
    if (defaultConfluenceId) {
      setConfluenceId(defaultConfluenceId);
    }
  }, [defaultConfluenceId]);

  useEffect(() => {
    if (defaultGithubOrg) {
      setGithubOrg(defaultGithubOrg);
    }
  }, [defaultGithubOrg]);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const handleSyncConfluence = async (e) => {
    e.preventDefault();
    if (syncingType) return;
    
    setSyncingType('confluence');
    setLogs(['🚀 Starting Confluence vector store synchronization...']);

    try {
      const response = await fetch('http://localhost:8000/api/sync/confluence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_page_id: confluenceId })
      });

      if (!response.ok) {
        throw new Error(`Sync server responded with ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'log') {
                setLogs((prev) => [...prev, data.message]);
              } else if (data.type === 'done') {
                const timestamp = new Date().toLocaleString();
                setLogs((prev) => [...prev, `🎉 Sync completed at ${timestamp}`]);
                if (onSyncSuccess) onSyncSuccess();
              }
            } catch (err) {
              // Ignore partial JSON parse errors
            }
          }
        }
      }
    } catch (err) {
      setLogs((prev) => [...prev, `❌ Error: ${err.message}`]);
    } finally {
      setSyncingType(null);
    }
  };

  const handleSyncGithub = async (e) => {
    e.preventDefault();
    if (syncingType) return;

    setSyncingType('github');
    setLogs(['🚀 Starting GitHub Repository vector store synchronization...']);

    try {
      const response = await fetch('http://localhost:8000/api/sync/github', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_name: githubOrg })
      });

      if (!response.ok) {
        throw new Error(`Sync server responded with ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'log') {
                setLogs((prev) => [...prev, data.message]);
              } else if (data.type === 'done') {
                const timestamp = new Date().toLocaleString();
                setLogs((prev) => [...prev, `🎉 Sync completed at ${timestamp}`]);
                if (onSyncSuccess) onSyncSuccess();
              }
            } catch (err) {
              // Ignore partial JSON parse errors
            }
          }
        }
      }
    } catch (err) {
      setLogs((prev) => [...prev, `❌ Error: ${err.message}`]);
    } finally {
      setSyncingType(null);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '20px', height: '100%', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Database className="glow-text-cyan" size={20} />
        <h2 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--accent-forest)' }}>Knowledge Sync Center</h2>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        {/* Confluence Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <form onSubmit={handleSyncConfluence} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>
              Confluence Parent Page ID
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                className="cyber-input"
                value={confluenceId}
                onChange={(e) => setConfluenceId(e.target.value)}
                placeholder="e.g. 100"
                required
                disabled={syncingType !== null}
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="cyber-btn"
                disabled={syncingType !== null}
                style={{ padding: '10px' }}
              >
                {syncingType === 'confluence' ? (
                  <RefreshCw className="animate-spin" size={16} style={{ animation: 'spin 2s linear infinite' }} />
                ) : (
                  <RefreshCw size={16} />
                )}
                Sync
              </button>
            </div>
          </form>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', paddingLeft: '2px' }}>
            Last sync: <span style={{ fontWeight: 500, color: 'var(--accent-forest)' }}>{lastConfluenceSync}</span>
          </div>
        </div>

        {/* GitHub Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <form onSubmit={handleSyncGithub} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>
              GitHub Organization Name
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                className="cyber-input"
                value={githubOrg}
                onChange={(e) => setGithubOrg(e.target.value)}
                placeholder="e.g. my-org"
                required
                disabled={syncingType !== null}
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="cyber-btn"
                disabled={syncingType !== null}
                style={{ padding: '10px' }}
              >
                {syncingType === 'github' ? (
                  <RefreshCw className="animate-spin" size={16} style={{ animation: 'spin 2s linear infinite' }} />
                ) : (
                  <RefreshCw size={16} />
                )}
                Sync
              </button>
            </div>
          </form>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', paddingLeft: '2px' }}>
            Last sync: <span style={{ fontWeight: 500, color: 'var(--accent-forest)' }}>{lastGithubSync}</span>
          </div>
        </div>
      </div>

      {/* Sync Logs Console */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '10px', minHeight: '180px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.75rem', borderBottom: '1px solid rgba(88, 129, 87, 0.15)', paddingBottom: '5px' }}>
          <Terminal size={14} />
          <span>Indexing Console Logs</span>
          {syncingType && <div className="pulse-indicator" style={{ marginLeft: 'auto' }} />}
        </div>
        <div
          className="terminal-font"
          style={{
            flex: 1,
            background: 'var(--bg-tertiary)',
            borderRadius: '6px',
            padding: '10px',
            overflowY: 'auto',
            maxHeight: '400px',
            border: '1px solid var(--border-glass)',
            color: 'var(--text-main)',
            lineHeight: '1.4'
          }}
        >
          {logs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.78rem' }}>
              No active logs. Trigger synchronization to index.
            </div>
          ) : (
            logs.map((log, index) => {
              let color = 'var(--text-main)'; // Default text
              if (log.startsWith('--> [KEEP]')) color = '#16a34a'; // Green keep
              else if (log.startsWith('--> [PRUNE]')) color = '#dc2626'; // Red prune
              else if (log.startsWith('✅') || log.startsWith('🎉')) color = '#15803d'; // Success
              else if (log.startsWith('❌')) color = '#ef4444'; // Error
              else if (log.startsWith('-->')) color = '#0284c7'; // Sub-step
              
              return (
                <div key={index} style={{ color, marginBottom: '4px', fontSize: '0.8rem', whiteSpace: 'pre-wrap' }}>
                  {log}
                </div>
              );
            })
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
