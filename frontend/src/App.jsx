import React, { useState, useEffect, useRef } from 'react';
import { Bot, User, Send, Wifi, WifiOff, Code, Layers, Loader2 } from 'lucide-react';
import SyncPanel from './components/SyncPanel';

// Simple parser to render markdown bolding and code blocks nicely
const renderMessageContent = (content) => {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);
  return parts.map((part, index) => {
    if (part.startsWith('```')) {
      // Extract language and code
      const match = part.match(/```(\w*)\n([\s\S]*?)```/);
      const language = match ? match[1] : 'code';
      const codeText = match ? match[2].trim() : part.slice(3, -3).trim();

      return (
        <div key={index} className="glass-panel" style={{ margin: '12px 0', border: '1px solid rgba(88, 129, 87, 0.25)', overflow: 'hidden', borderRadius: '8px' }}>
          <div style={{ background: 'rgba(88, 129, 87, 0.08)', padding: '6px 14px', borderBottom: '1px solid rgba(88, 129, 87, 0.15)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="terminal-font" style={{ fontSize: '0.75rem', color: 'var(--accent-forest)', fontWeight: 600, textTransform: 'uppercase' }}>
              {language || 'code'}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(codeText)}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '0.7rem', cursor: 'pointer' }}
              className="glow-text-cyan-hover"
            >
              Copy
            </button>
          </div>
          <pre style={{ margin: 0, padding: '12px', overflowX: 'auto', background: '#f8faf9' }}>
            <code className="terminal-font" style={{ fontSize: '0.8rem', color: 'var(--text-main)', display: 'block' }}>{codeText}</code>
          </pre>
        </div>
      );
    }

    // Process inline bold text **text** and linebreaks
    const textLines = part.split('\n').map((line, lIdx) => {
      const boldParts = line.split(/(\*\*.*?\*\*)/g);
      return (
        <span key={lIdx} style={{ display: 'block', marginBottom: line === '' ? '10px' : '3px' }}>
          {boldParts.map((subPart, pIdx) => {
            if (subPart.startsWith('**') && subPart.endsWith('**')) {
              return <strong key={pIdx} style={{ color: 'var(--accent-forest)' }}>{subPart.slice(2, -2)}</strong>;
            }
            return subPart;
          })}
        </span>
      );
    });

    return <span key={index}>{textLines}</span>;
  });
};

function App() {
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      content: 'Hello! I am your agentic assistant. I can search Confluence, GitHub, and Jira to help answer architectural, code-level, or task-level questions. Ask me anything, or index repositories/pages using the sync panel.'
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [healthStatus, setHealthStatus] = useState({ status: 'offline', has_openai_key: false, has_google_key: false, active_provider: 'none' });
  const [agentStatusLogs, setAgentStatusLogs] = useState([]);
  
  const messagesEndRef = useRef(null);

  // Auto-scroll hook
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Load server health configuration on load
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/health');
        if (response.ok) {
          const data = await response.json();
          setHealthStatus(data);
        } else {
          setHealthStatus({ status: 'error', has_openai_key: false, has_google_key: false, active_provider: 'none' });
        }
      } catch (err) {
        setHealthStatus({ status: 'offline', has_openai_key: false, has_google_key: false, active_provider: 'none' });
      }
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userQuery = input.trim();
    setInput('');
    setLoading(true);
    // Initialize with a clean plan start status
    setAgentStatusLogs(['Initializing agent execution...']);
    
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userQuery },
      { role: 'ai', content: '', loading: true }
    ]);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userQuery })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to communicate with agent');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiResponseText = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'status') {
                setAgentStatusLogs((prev) => [...prev, data.message]);
              } else if (data.type === 'content') {
                aiResponseText += data.content;
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  lastMsg.content = aiResponseText;
                  lastMsg.loading = false;
                  return updated;
                });
              } else if (data.type === 'error') {
                setAgentStatusLogs((prev) => [...prev, `❌ Error: ${data.message}`]);
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  lastMsg.content = `⚠️ An error occurred while executing the task: ${data.message}`;
                  lastMsg.loading = false;
                  lastMsg.isError = true;
                  return updated;
                });
              }
            } catch (err) {
              // Ignore partial stream line parse errors
            }
          }
        }
      }
    } catch (err) {
      setAgentStatusLogs((prev) => [...prev, `❌ Exception: ${err.message}`]);
      setMessages((prev) => {
        const updated = [...prev];
        const lastMsg = updated[updated.length - 1];
        lastMsg.content = `⚠️ An error occurred while executing the task: ${err.message}. Please verify the backend is running and credentials are set.`;
        lastMsg.loading = false;
        lastMsg.isError = true;
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  // Get current active task text
  const currentTaskText = agentStatusLogs.length > 0 ? agentStatusLogs[agentStatusLogs.length - 1] : '';

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', padding: '16px', gap: '16px' }}>
      
      {/* Top Header Bar */}
      <header className="glass-panel" style={{ padding: '12px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-glass)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Layers className="glow-text-cyan" size={24} style={{ color: 'var(--accent-forest)' }} />
          <div>
            <h1 className="glow-text-cyan" style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--accent-forest)' }}>
              AEGIS-CHATBOT
            </h1>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '1px', textTransform: 'uppercase', fontWeight: 500 }}>
              Agentic Enterprise Knowledge Integrator
            </span>
          </div>
        </div>

        {/* Connection/Model Pills */}
        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          
          {/* Active Model Pill */}
          <div style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid rgba(88, 129, 87, 0.2)',
            borderRadius: '16px',
            padding: '4px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.75rem',
            color: 'var(--accent-forest)',
            fontWeight: 500
          }}>
            <Code size={12} />
            <span>LLM: {healthStatus.active_provider === 'google' ? 'Gemini Flash' : (healthStatus.active_provider === 'openai' ? 'OpenAI GPT' : 'No Keys')}</span>
          </div>

          {/* Connection Pill */}
          <div style={{
            background: healthStatus.status === 'healthy' ? 'rgba(88, 129, 87, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            border: `1px solid ${healthStatus.status === 'healthy' ? 'rgba(88, 129, 87, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
            borderRadius: '16px',
            padding: '4px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.75rem',
            color: healthStatus.status === 'healthy' ? 'var(--accent-forest)' : '#ef4444',
            fontWeight: 500
          }}>
            {healthStatus.status === 'healthy' ? <Wifi size={12} /> : <WifiOff size={12} />}
            <span>Server: {healthStatus.status.toUpperCase()}</span>
          </div>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <main style={{ flex: 1, display: 'grid', gridTemplateColumns: '1.85fr 1fr', gap: '16px', minHeight: 0 }}>
        
        {/* Left Side: Agent Chat cockpit */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px', minHeight: 0 }}>
          
          {/* Chat message space */}
          <div className="glass-panel" style={{ flex: 1, padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto', minHeight: 0 }}>
            {messages.map((msg, index) => (
              <div
                key={index}
                className="animate-slide-up"
                style={{
                  display: 'flex',
                  gap: '12px',
                  alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
                }}
              >
                {/* Avatar Icon */}
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: msg.role === 'user' ? 'var(--bg-tertiary)' : (msg.isError ? 'rgba(239, 68, 68, 0.08)' : 'rgba(88, 129, 87, 0.08)'),
                  border: `1px solid ${msg.role === 'user' ? 'rgba(88, 129, 87, 0.3)' : (msg.isError ? 'rgba(239, 68, 68, 0.3)' : 'var(--border-glass)')}`,
                  boxShadow: msg.role === 'user' ? 'none' : 'var(--text-glow)'
                }}>
                  {msg.role === 'user' ? <User size={16} color="var(--accent-forest)" /> : <Bot size={16} color={msg.isError ? '#ef4444' : 'var(--accent-green)'} />}
                </div>

                {/* Message bubble body */}
                <div style={{
                  background: msg.isError ? 'rgba(239, 68, 68, 0.04)' : (msg.role === 'user' ? 'rgba(132, 169, 140, 0.15)' : 'var(--bg-secondary)'),
                  border: `1px solid ${msg.isError ? 'rgba(239, 68, 68, 0.25)' : (msg.role === 'user' ? 'rgba(132, 169, 140, 0.3)' : 'var(--border-glass)')}`,
                  borderRadius: msg.role === 'user' ? '12px 2px 12px 12px' : '2px 12px 12px 12px',
                  padding: '12px 16px',
                  fontSize: '0.92rem',
                  lineHeight: '1.5',
                  color: msg.isError ? '#dc2626' : 'var(--text-main)',
                  boxShadow: '0 2px 8px rgba(88, 129, 87, 0.02)'
                }}>
                  {msg.loading ? (
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '4px 0' }}>
                      <Loader2 className="animate-spin" size={14} style={{ color: 'var(--accent-green)', animation: 'spin 1.5s linear infinite' }} />
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Thinking...</span>
                    </div>
                  ) : (
                    renderMessageContent(msg.content)
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Dynamic "Current Task" Badge (ChatGPT/Gemini Style) */}
          {loading && currentTaskText && !currentTaskText.startsWith('❌') && (
            <div className="glass-panel" style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: '20px',
              fontSize: '0.82rem',
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(88, 129, 87, 0.2)',
              boxShadow: '0 2px 8px rgba(88, 129, 87, 0.05)',
              alignSelf: 'flex-start',
              marginLeft: '4px',
              animation: 'slide-up 0.2s ease-out'
            }}>
              <span className="pulse-indicator" style={{ display: 'inline-block' }} />
              <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
                {currentTaskText}
              </span>
            </div>
          )}

          {/* Form chat input */}
          <form onSubmit={handleSend} style={{ display: 'flex', gap: '10px' }}>
            <input
              type="text"
              className="cyber-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={healthStatus.status !== 'healthy' ? "Connecting to backend..." : "Ask about service configurations, PR details, user validation routes..."}
              disabled={loading || healthStatus.status !== 'healthy'}
              style={{ flex: 1, padding: '14px 20px', fontSize: '0.98rem' }}
            />
            <button
              type="submit"
              className="cyber-btn"
              disabled={loading || !input.trim() || healthStatus.status !== 'healthy'}
              style={{ padding: '0 24px' }}
            >
              <Send size={18} />
              Send
            </button>
          </form>

        </section>

        {/* Right Side: Sync Center Panel */}
        <section style={{ height: '100%' }}>
          <SyncPanel />
        </section>

      </main>
    </div>
  );
}

export default App;
