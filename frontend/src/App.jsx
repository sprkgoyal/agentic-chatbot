import React, { useState, useEffect, useRef } from 'react';
import { 
  Bot, User, Send, Wifi, WifiOff, Code, Layers, Loader2, 
  Trash2, Download, Settings, LogOut, Shield, Database, 
  Terminal, RefreshCw, Plus, CheckCircle, Circle, AlertCircle 
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const PRE_SEEDED_AVATARS = [
  { id: 'avatar_1', emoji: '🐸', label: 'Frog' },
  { id: 'avatar_2', emoji: '🐨', label: 'Koala' },
  { id: 'avatar_3', emoji: '🐼', label: 'Panda' },
  { id: 'avatar_4', emoji: '🦊', label: 'Fox' },
  { id: 'avatar_5', emoji: '🦁', label: 'Lion' },
  { id: 'avatar_6', emoji: '🐰', label: 'Rabbit' },
  { id: 'avatar_7', emoji: '🦉', label: 'Owl' },
  { id: 'avatar_8', emoji: '🐢', label: 'Turtle' }
];

const getAvatarEmoji = (picId) => {
  const av = PRE_SEEDED_AVATARS.find(a => a.id === picId);
  return av ? av.emoji : '👤';
};

// Markdown code block renderer with copy button
const renderMessageContent = (content) => {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);
  return parts.map((part, index) => {
    if (part.startsWith('```')) {
      const match = part.match(/```(\w*)\n([\s\S]*?)```/);
      const language = match ? match[1] : 'code';
      const codeText = match ? match[2].trim() : part.slice(3, -3).trim();

      return (
        <div key={index} className="glass-panel" style={{ margin: '12px 0', border: '1px solid var(--border-glass)', overflow: 'hidden', borderRadius: '10px' }}>
          <div style={{ background: 'rgba(88, 129, 87, 0.08)', padding: '8px 16px', borderBottom: '1px solid var(--border-glass)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="terminal-font" style={{ fontSize: '0.75rem', color: 'var(--accent-forest)', fontWeight: 600, textTransform: 'uppercase' }}>
              {language || 'code'}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(codeText)}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 500 }}
            >
              Copy
            </button>
          </div>
          <pre style={{ margin: 0, padding: '14px', overflowX: 'auto', background: '#fafbfc' }}>
            <code className="terminal-font" style={{ fontSize: '0.8rem', color: 'var(--text-main)', display: 'block' }}>{codeText}</code>
          </pre>
        </div>
      );
    }

    // Process inline bold text **text** and linebreaks
    const textLines = part.split('\n').map((line, lIdx) => {
      const boldParts = line.split(/(\*\*.*?\*\*)/g);
      return (
        <span key={lIdx} style={{ display: 'block', marginBottom: line === '' ? '12px' : '4px' }}>
          {boldParts.map((subPart, pIdx) => {
            if (subPart.startsWith('**') && subPart.endsWith('**')) {
              return <strong key={pIdx} style={{ color: 'var(--accent-forest)', fontWeight: 600 }}>{subPart.slice(2, -2)}</strong>;
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
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [user, setUser] = useState(null);
  
  // Auth Form State
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('customer');
  const [authError, setAuthError] = useState('');

  // App Common State
  const [serverHealth, setServerHealth] = useState({ status: 'offline', active_provider: 'none' });

  // Customer Chat State
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [activeStatusLogs, setActiveStatusLogs] = useState([]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Settings Form State
  const [settingsName, setSettingsName] = useState('');
  const [settingsAvatar, setSettingsAvatar] = useState('avatar_1');
  const [settingsMessage, setSettingsMessage] = useState('');

  // Admin Space Sync State
  const [spaceId, setSpaceId] = useState('ENG');
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncLogs, setSyncLogs] = useState([]);

  const messagesEndRef = useRef(null);
  const syncLogsEndRef = useRef(null);

  // Health Polling
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/health`);
        if (response.ok) {
          const data = await response.json();
          setServerHealth(data);
        } else {
          setServerHealth({ status: 'offline', active_provider: 'none' });
        }
      } catch (err) {
        setServerHealth({ status: 'offline', active_provider: 'none' });
      }
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Fetch logged in profile
  useEffect(() => {
    if (token) {
      const fetchProfile = async () => {
        try {
          const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (res.ok) {
            const data = await res.json();
            setUser(data);
            setSettingsName(data.name);
            setSettingsAvatar(data.userpic);
          } else {
            // Token expired/invalid
            handleLogout();
          }
        } catch (err) {
          handleLogout();
        }
      };
      fetchProfile();
    } else {
      setUser(null);
    }
  }, [token]);

  // Fetch conversations (only for customer)
  useEffect(() => {
    if (user && user.role === 'customer') {
      fetchConversations();
    }
  }, [user]);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (activeConvId && user && user.role === 'customer') {
      fetchMessages(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  // Auto-scroll chats
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeStatusLogs]);

  // Auto-scroll sync console
  useEffect(() => {
    if (syncLogsEndRef.current) {
      syncLogsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [syncLogs]);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/conversations`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
        if (data.length > 0 && !activeConvId) {
          setActiveConvId(data[0].id);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchMessages = async (convId) => {
    try {
      const res = await fetch(`${API_BASE}/api/conversations/${convId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    if (!username.trim()) return;

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, role })
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('token', data.token);
        setToken(data.token);
        setUser(data.user);
      } else {
        const errData = await res.json();
        setAuthError(errData.detail || 'Login failed.');
      }
    } catch (err) {
      setAuthError('Connection server error. Verify backend is running.');
    }
  };

  const handleLogout = () => {
    if (token) {
      fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      }).catch(() => {});
    }
    localStorage.removeItem('token');
    setToken('');
    setUser(null);
    setConversations([]);
    setActiveConvId('');
    setMessages([]);
  };

  const handleCreateConversation = async () => {
    try {
      const title = `Chat: Spec Sync ${new Date().toLocaleDateString()}`;
      const res = await fetch(`${API_BASE}/api/conversations`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ title })
      });
      if (res.ok) {
        const newConv = await res.json();
        setConversations(prev => [newConv, ...prev]);
        setActiveConvId(newConv.id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteConversation = async (convId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/conversations/${convId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== convId));
        if (activeConvId === convId) {
          setActiveConvId('');
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDownloadConversation = async (convId, e) => {
    e.stopPropagation();
    try {
      window.open(`${API_BASE}/api/conversations/${convId}/download?token=${token}`, '_blank');
      // Alternative: fetch log directly
      const res = await fetch(`${API_BASE}/api/conversations/${convId}/download`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const text = await res.text();
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `chat_${convId}.txt`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleUpdateSettings = async (e) => {
    e.preventDefault();
    setSettingsMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/user/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ name: settingsName, userpic: settingsAvatar })
      });
      if (res.ok) {
        setUser(prev => ({ ...prev, name: settingsName, userpic: settingsAvatar }));
        setSettingsMessage('Settings saved successfully!');
        setTimeout(() => setIsSettingsOpen(false), 800);
      } else {
        const errData = await res.json();
        setSettingsMessage(`Error: ${errData.detail}`);
      }
    } catch (err) {
      setSettingsMessage('Failed to connect to server.');
    }
  };

  const handleDeleteAccount = async () => {
    if (!confirm('CRITICAL WARNING: This will permanently delete your account, settings, and all chats. Proceed?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/auth/delete-account`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        alert('Account deleted successfully.');
        handleLogout();
      } else {
        alert('Failed to delete account.');
      }
    } catch (err) {
      alert('Error connecting to server.');
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || chatLoading || !activeConvId) return;

    const query = input.trim();
    setInput('');
    setChatLoading(true);
    setActiveStatusLogs(['Initializing agent graphs...']);

    // Append temporary messages to UI local list
    setMessages(prev => [
      ...prev,
      { role: 'user', content: query, created_at: new Date().toISOString() },
      { role: 'ai', content: '', loading: true, status_logs: [], created_at: new Date().toISOString() }
    ]);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ message: query, conversation_id: activeConvId })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Server error');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = '';

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
                setActiveStatusLogs(prev => [...prev, data.message]);
              } else if (data.type === 'content') {
                accumulatedContent += data.content;
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  last.content = accumulatedContent;
                  last.loading = false;
                  return updated;
                });
              } else if (data.type === 'error') {
                setActiveStatusLogs(prev => [...prev, `❌ Error: ${data.message}`]);
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  last.content = `⚠️ Executing error: ${data.message}`;
                  last.loading = false;
                  last.is_error = true;
                  return updated;
                });
              }
            } catch (e) {}
          }
        }
      }
    } catch (err) {
      setActiveStatusLogs(prev => [...prev, `❌ Exception: ${err.message}`]);
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        last.content = `⚠️ Streaming failure: ${err.message}. Verify network connectivity.`;
        last.loading = false;
        last.is_error = true;
        return updated;
      });
    } finally {
      setChatLoading(false);
      // Reload final messages from backend database to ensure alignment and persistent status logs
      fetchMessages(activeConvId);
      setActiveStatusLogs([]);
    }
  };

  const handleSyncConfluenceSpace = async (e) => {
    e.preventDefault();
    if (!spaceId.trim() || isSyncing) return;

    setIsSyncing(true);
    setSyncLogs(['🚀 Initializing Confluence space crawler using CQL...']);

    try {
      const response = await fetch(`${API_BASE}/api/sync/confluence`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ space_id: spaceId.trim() })
      });

      if (!response.ok) {
        throw new Error(`Sync server returned HTTP ${response.status}`);
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
                setSyncLogs(prev => [...prev, data.message]);
              } else if (data.type === 'done') {
                const stamp = new Date().toLocaleTimeString();
                setSyncLogs(prev => [...prev, `🎉 Index sync complete at ${stamp}`]);
              }
            } catch (err) {}
          }
        }
      }
    } catch (err) {
      setSyncLogs(prev => [...prev, `❌ Sync failure: ${err.message}`]);
    } finally {
      setIsSyncing(false);
    }
  };

  // --- Rendering Functions ---

  // Renders the checklist / TODO list generated by deepagents
  const renderAgentChecklist = (logsList) => {
    if (!logsList || logsList.length === 0) return null;
    
    // Find if agent compiled a TODO list or tool logs
    return (
      <div className="agent-checklist">
        <div className="agent-checklist-title">
          <Terminal size={14} />
          <span>Agent Checklist & Execution Steps</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {logsList.map((log, idx) => {
            const isCompleted = log.startsWith('✅') || log.startsWith('🛠️ Agent invoking tool');
            const isErr = log.startsWith('❌') || log.startsWith('⚠️');
            return (
              <div key={idx} className={`checklist-item ${isCompleted ? 'done' : ''}`} style={{ fontSize: '0.78rem' }}>
                {isErr ? (
                  <AlertCircle size={12} color="#ef4444" />
                ) : isCompleted ? (
                  <CheckCircle size={12} color="var(--accent-green)" />
                ) : (
                  <Circle size={12} color="var(--text-muted)" />
                )}
                <span>{log}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (!token || !user) {
    // ---------------- SIGN IN UI ----------------
    return (
      <div className="login-container">
        <div className="glass-panel login-card animate-slide-up">
          <div className="login-logo">
            <Layers size={40} style={{ color: 'var(--accent-green)', marginRight: '8px' }} />
            <div>
              <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent-forest)', letterSpacing: '-0.5px' }}>
                AEGIS PORTAL
              </h1>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 600 }}>
                Knowledge Base Sync & Chat
              </span>
            </div>
          </div>

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px', textAlign: 'left' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>Username</label>
              <input
                type="text"
                className="cyber-input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Enter username"
                required
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>Workspace Portal</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <button
                  type="button"
                  className="cyber-btn-outline"
                  onClick={() => setRole('customer')}
                  style={{
                    borderColor: role === 'customer' ? 'var(--accent-forest)' : 'var(--border-glass)',
                    background: role === 'customer' ? 'var(--bg-tertiary)' : 'transparent',
                    color: 'var(--text-main)',
                    fontWeight: role === 'customer' ? 600 : 400
                  }}
                >
                  <Bot size={16} color="var(--accent-green)" />
                  Customer Chat
                </button>
                <button
                  type="button"
                  className="cyber-btn-outline"
                  onClick={() => setRole('admin')}
                  style={{
                    borderColor: role === 'admin' ? 'var(--accent-forest)' : 'var(--border-glass)',
                    background: role === 'admin' ? 'var(--bg-tertiary)' : 'transparent',
                    color: 'var(--text-main)',
                    fontWeight: role === 'admin' ? 600 : 400
                  }}
                >
                  <Shield size={16} color="var(--accent-forest)" />
                  Admin Control
                </button>
              </div>
            </div>

            {authError && (
              <div style={{ color: '#ef4444', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <AlertCircle size={14} />
                <span>{authError}</span>
              </div>
            )}

            <button type="submit" className="cyber-btn" style={{ padding: '14px', fontSize: '1rem', marginTop: '10px' }}>
              Access Portal
            </button>
          </form>

          <div style={{ marginTop: '24px', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            System will automatically create the user account on first login.
          </div>
        </div>
      </div>
    );
  }

  if (user.role === 'admin') {
    // ---------------- ADMIN PORTAL ----------------
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', padding: '24px', gap: '24px' }}>
        
        {/* Header */}
        <header className="glass-panel animate-slide-up" style={{ padding: '16px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Shield size={28} style={{ color: 'var(--accent-forest)' }} />
            <div>
              <h1 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-forest)' }}>
                AEGIS CONTROL PANEL
              </h1>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 600 }}>
                Vector Database Index Sync Only
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            {/* Health */}
            <div style={{
              background: serverHealth.status === 'healthy' ? 'rgba(88, 129, 87, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              border: `1px solid ${serverHealth.status === 'healthy' ? 'rgba(88, 129, 87, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
              borderRadius: '20px',
              padding: '6px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.75rem',
              color: serverHealth.status === 'healthy' ? 'var(--accent-forest)' : '#ef4444',
              fontWeight: 600
            }}>
              {serverHealth.status === 'healthy' ? <Wifi size={12} /> : <WifiOff size={12} />}
              <span>Server: {serverHealth.status.toUpperCase()}</span>
            </div>

            <button onClick={handleLogout} className="cyber-btn-outline" style={{ padding: '8px 14px', fontSize: '0.8rem' }}>
              <LogOut size={14} />
              Logout
            </button>
          </div>
        </header>

        {/* Main Sync Work Area */}
        <main style={{ flex: 1, display: 'grid', gridTemplateColumns: '1.2fr 2fr', gap: '24px', minHeight: 0 }} className="animate-slide-up">
          {/* Sync control form */}
          <section className="glass-panel" style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Database size={20} color="var(--accent-forest)" />
              <h2 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--accent-forest)' }}>Knowledge Sync Center</h2>
            </div>
            
            <form onSubmit={handleSyncConfluenceSpace} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  Confluence Space ID (Key)
                </label>
                <input
                  type="text"
                  className="cyber-input"
                  value={spaceId}
                  onChange={e => setSpaceId(e.target.value)}
                  placeholder="e.g. ENG, SPEC"
                  required
                  disabled={isSyncing}
                />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  Indexes all documents from the specified space key using Confluence Query Language (CQL).
                </span>
              </div>

              <button type="submit" className="cyber-btn" disabled={isSyncing || serverHealth.status !== 'healthy'}>
                {isSyncing ? (
                  <>
                    <RefreshCw className="animate-spin" size={16} />
                    Syncing Space docs...
                  </>
                ) : (
                  <>
                    <RefreshCw size={16} />
                    Trigger Space Index Sync
                  </>
                )}
              </button>
            </form>
          </section>

          {/* Indexing Logs output Console */}
          <section className="glass-panel" style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-glass)', paddingBottom: '8px', color: 'var(--text-muted)' }}>
              <Terminal size={16} />
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Indexing Sync Logs Console</span>
              {isSyncing && <div className="pulse-indicator" style={{ marginLeft: 'auto' }} />}
            </div>

            <div
              className="terminal-font"
              style={{
                flex: 1,
                background: 'rgba(88, 129, 87, 0.04)',
                border: '1px solid var(--border-glass)',
                borderRadius: '10px',
                padding: '16px',
                overflowY: 'auto',
                lineHeight: '1.5'
              }}
            >
              {syncLogs.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.8rem' }}>
                  No active logs. Specify a Space ID and trigger index sync to see crawler progress.
                </div>
              ) : (
                syncLogs.map((log, idx) => {
                  let color = 'var(--text-main)';
                  if (log.startsWith('✅') || log.startsWith('🎉')) color = '#15803d';
                  else if (log.startsWith('❌')) color = '#ef4444';
                  else if (log.startsWith('🚀') || log.startsWith('-> Page ID')) color = 'var(--accent-forest)';
                  return (
                    <div key={idx} style={{ color, marginBottom: '6px', fontSize: '0.8rem' }}>
                      {log}
                    </div>
                  );
                })
              )}
              <div ref={syncLogsEndRef} />
            </div>
          </section>
        </main>
      </div>
    );
  }

  // ---------------- CUSTOMER PORTAL ----------------
  return (
    <div style={{ height: '100vh', display: 'flex', padding: '16px', gap: '16px', overflow: 'hidden' }}>
      
      {/* Sidebar navigation */}
      <aside className="glass-panel sidebar animate-slide-up" style={{ minWidth: '280px' }}>
        
        {/* Header & New Chat */}
        <div className="sidebar-header" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={22} color="var(--accent-green)" />
            <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent-forest)' }}>AEGIS DESK</h2>
          </div>
          
          <button onClick={handleCreateConversation} className="cyber-btn" style={{ padding: '10px', fontSize: '0.85rem' }}>
            <Plus size={16} />
            New Spec Chat
          </button>
        </div>

        {/* Chats History list */}
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.8rem', textAlign: 'center', padding: '20px 0' }}>
              No chats yet. Create a conversation to start.
            </div>
          ) : (
            conversations.map(conv => (
              <div 
                key={conv.id} 
                className={`conversation-item ${activeConvId === conv.id ? 'active' : ''}`}
                onClick={() => setActiveConvId(conv.id)}
              >
                <span className="conversation-title">{conv.title}</span>
                <div className="conversation-actions">
                  <button 
                    onClick={(e) => handleDownloadConversation(conv.id, e)} 
                    className="action-btn"
                    title="Download chat logs"
                  >
                    <Download size={12} />
                  </button>
                  <button 
                    onClick={(e) => handleDeleteConversation(conv.id, e)} 
                    className="action-btn action-btn-danger"
                    title="Delete chat"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Bottom Profile Settings footer panel */}
        <div className="sidebar-footer" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '50%',
              background: 'rgba(88, 129, 87, 0.1)',
              border: '1px solid var(--border-glass)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.4rem'
            }}>
              {getAvatarEmoji(user.userpic)}
            </div>
            <div style={{ maxWidth: '140px', overflow: 'hidden' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                {user.name}
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 500 }}>
                {user.username}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '4px' }}>
            <button onClick={() => setIsSettingsOpen(true)} className="action-btn" title="Profile Settings">
              <Settings size={16} />
            </button>
            <button onClick={handleLogout} className="action-btn action-btn-danger" title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main chat center */}
      <section style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '12px', minHeight: 0 }} className="animate-slide-up">
        
        {/* Top bar info */}
        <header className="glass-panel" style={{ padding: '12px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--accent-forest)' }}>
            {activeConvId 
              ? (conversations.find(c => c.id === activeConvId)?.title || 'Current Spec Thread')
              : 'AEGIS Enterprise Support'
            }
          </h2>

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            {/* Active LLM Provider */}
            <div style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid rgba(88, 129, 87, 0.2)',
              borderRadius: '20px',
              padding: '4px 12px',
              fontSize: '0.72rem',
              color: 'var(--accent-forest)',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}>
              <Code size={10} />
              <span>Provider: {serverHealth.active_provider === 'google' ? 'Gemini' : (serverHealth.active_provider === 'openai' ? 'GPT-4' : 'N/A')}</span>
            </div>

            {/* Health status */}
            <div style={{
              background: serverHealth.status === 'healthy' ? 'rgba(88, 129, 87, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              border: `1px solid ${serverHealth.status === 'healthy' ? 'rgba(88, 129, 87, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
              borderRadius: '20px',
              padding: '4px 12px',
              fontSize: '0.72rem',
              color: serverHealth.status === 'healthy' ? 'var(--accent-forest)' : '#ef4444',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}>
              {serverHealth.status === 'healthy' ? <Wifi size={10} /> : <WifiOff size={10} />}
              <span>{serverHealth.status.toUpperCase()}</span>
            </div>
          </div>
        </header>

        {/* Message board space */}
        <div className="glass-panel" style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto', minHeight: 0 }}>
          {!activeConvId ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '16px', color: 'var(--text-muted)' }}>
              <Layers size={48} style={{ color: 'var(--accent-mint)' }} />
              <div style={{ textAlign: 'center' }}>
                <h3 style={{ color: 'var(--accent-forest)', fontWeight: 600, marginBottom: '4px' }}>Welcome to AEGIS spec workspace</h3>
                <p style={{ fontSize: '0.85rem' }}>Select a conversation from the sidebar history or create a new session to query spec manuals.</p>
              </div>
            </div>
          ) : messages.length === 0 && !chatLoading ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '12px', color: 'var(--text-muted)' }}>
              <Bot size={40} style={{ color: 'var(--accent-mint)' }} />
              <div style={{ textAlign: 'center', fontSize: '0.85rem' }}>
                <p>No queries logged in this thread yet. Ask anything about internal architecture specs.</p>
                <p style={{ fontSize: '0.75rem', fontStyle: 'italic', marginTop: '6px', opacity: 0.8 }}>
                  Example: "What are the specs for User Service?" or "Search confluence space 'DS'"
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => (
                <div 
                  key={msg.id || index}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
                  }}
                >
                  {/* Avatar bubble */}
                  <div style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: msg.role === 'user' ? 'rgba(88, 129, 87, 0.08)' : (msg.is_error ? 'rgba(239, 68, 68, 0.08)' : 'rgba(88, 129, 87, 0.08)'),
                    border: `1px solid ${msg.role === 'user' ? 'var(--accent-green)' : (msg.is_error ? 'rgba(239, 68, 68, 0.3)' : 'var(--border-glass)')}`,
                    boxShadow: 'var(--box-shadow-soft)',
                    fontSize: msg.role === 'user' ? '1.3rem' : '1rem'
                  }}>
                    {msg.role === 'user' ? getAvatarEmoji(user.userpic) : <Bot size={18} color={msg.is_error ? '#ef4444' : 'var(--accent-green)'} />}
                  </div>

                  {/* Message content block */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{
                      background: msg.is_error ? 'rgba(239, 68, 68, 0.04)' : (msg.role === 'user' ? 'var(--bg-tertiary)' : 'var(--bg-secondary)'),
                      border: `1px solid ${msg.is_error ? 'rgba(239, 68, 68, 0.25)' : (msg.role === 'user' ? 'rgba(88, 129, 87, 0.25)' : 'var(--border-glass)')}`,
                      borderRadius: msg.role === 'user' ? '14px 2px 14px 14px' : '2px 14px 14px 14px',
                      padding: '14px 18px',
                      fontSize: '0.92rem',
                      lineHeight: '1.6',
                      color: msg.is_error ? '#dc2626' : 'var(--text-main)',
                      boxShadow: '0 2px 8px rgba(58, 90, 64, 0.02)'
                    }}>
                      {msg.loading ? (
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '4px 0' }}>
                          <Loader2 className="animate-spin" size={14} style={{ color: 'var(--accent-green)' }} />
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Thinking & executing tools...</span>
                        </div>
                      ) : (
                        renderMessageContent(msg.content)
                      )}
                    </div>

                    {/* Render execution steps / checklists under the response */}
                    {msg.role === 'ai' && renderAgentChecklist(msg.status_logs)}
                  </div>
                </div>
              ))}
              
              {/* Dynamic live checklist log during loading state */}
              {chatLoading && activeStatusLogs.length > 0 && (
                <div style={{ display: 'flex', gap: '12px', alignSelf: 'flex-start', maxWidth: '85%' }}>
                  <div style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'rgba(88, 129, 87, 0.08)',
                    border: '1px solid var(--border-glass)'
                  }}>
                    <Loader2 className="animate-spin" size={18} style={{ color: 'var(--accent-green)' }} />
                  </div>
                  <div>
                    {renderAgentChecklist(activeStatusLogs)}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input box form */}
        <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            className="cyber-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={!activeConvId 
              ? "Select a conversation to write queries..." 
              : (serverHealth.status !== 'healthy' ? "Connecting to backend..." : "Ask assistant about API gateway, Spec changes, confluence documents...")
            }
            disabled={!activeConvId || chatLoading || serverHealth.status !== 'healthy'}
            style={{ flex: 1, padding: '16px' }}
          />
          <button 
            type="submit" 
            className="cyber-btn"
            disabled={!activeConvId || chatLoading || !input.trim() || serverHealth.status !== 'healthy'}
            style={{ padding: '0 28px' }}
          >
            <Send size={18} />
            Send
          </button>
        </form>

      </section>

      {/* Profile Settings Modal Overlay */}
      {isSettingsOpen && (
        <div className="modal-overlay">
          <div className="glass-panel modal-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-glass)', paddingBottom: '12px', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings size={18} color="var(--accent-forest)" />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent-forest)' }}>Profile Settings</h3>
              </div>
              <button 
                onClick={() => { setIsSettingsOpen(false); setSettingsMessage(''); }}
                style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: 'var(--text-muted)' }}
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleUpdateSettings} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Your Name</label>
                <input
                  type="text"
                  className="cyber-input"
                  value={settingsName}
                  onChange={e => setSettingsName(e.target.value)}
                  placeholder="Enter name"
                  required
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Choose Avatar</label>
                <div className="avatar-grid">
                  {PRE_SEEDED_AVATARS.map(av => (
                    <div 
                      key={av.id}
                      className={`avatar-item ${settingsAvatar === av.id ? 'selected' : ''}`}
                      onClick={() => setSettingsAvatar(av.id)}
                      title={av.label}
                    >
                      {av.emoji}
                    </div>
                  ))}
                </div>
              </div>

              {settingsMessage && (
                <div style={{ 
                  fontSize: '0.8rem', 
                  color: settingsMessage.startsWith('Settings') ? 'var(--accent-forest)' : '#ef4444', 
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}>
                  {settingsMessage.startsWith('Settings') ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                  <span>{settingsMessage}</span>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid var(--border-glass)', paddingTop: '16px', marginTop: '12px' }}>
                <button 
                  type="button" 
                  onClick={handleDeleteAccount} 
                  className="cyber-btn-danger" 
                  style={{ marginRight: 'auto', padding: '10px 14px', fontSize: '0.8rem' }}
                >
                  Delete Account
                </button>
                <button 
                  type="button" 
                  onClick={() => { setIsSettingsOpen(false); setSettingsMessage(''); }} 
                  className="cyber-btn-outline"
                  style={{ padding: '10px 16px', fontSize: '0.85rem' }}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="cyber-btn"
                  style={{ padding: '10px 18px', fontSize: '0.85rem' }}
                >
                  Save Settings
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
