import React, { useState, useRef, useEffect } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function WorkPilotChat() {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [transactions, setTransactions] = useState([]);
  const [selectedTx, setSelectedTx] = useState(null);
  const [showThoughtChain, setShowThoughtChain] = useState({});

  const messagesEndRef = useRef(null);

  // Fetch real-time Transaction History for sidebar
  const fetchTransactions = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/transactions`);
      if (res.ok) {
        const data = await res.json();
        setTransactions(data);
      }
    } catch (err) {
      console.error('Failed to fetch transaction history:', err);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, selectedTx]);

  const toggleThoughtChain = (index) => {
    setShowThoughtChain((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  // Redirect & load single transaction view
  const handleRedirectToTransaction = async (txId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/transactions/${txId}`);
      if (res.ok) {
        const txData = await res.json();
        setSelectedTx(txData);
      }
    } catch (err) {
      console.error(`Failed to load transaction #${txId}:`, err);
    }
  };

  const parseMessageContent = (rawText) => {
    if (!rawText) return { bodyText: '', actionButtons: [] };

    if (rawText.includes('---ACTION_BUTTONS---')) {
      const parts = rawText.split('---ACTION_BUTTONS---');
      const bodyText = parts[0].trim();
      try {
        const actionButtons = JSON.parse(parts[1].trim());
        return { bodyText, actionButtons };
      } catch (e) {
        return { bodyText, actionButtons: [] };
      }
    }
    return { bodyText: rawText, actionButtons: [] };
  };

  const handleSendPrompt = async (textToSend) => {
    setSelectedTx(null); // Return to active task feed
    const query = textToSend || prompt;
    if (!query.trim() || loading) return;

    // Intercept "View transaction history details for ID <X>" buttons
    const matchTxCmd = query.match(/ID\s*(\d+)/i) || query.match(/#(\d+)/);
    if (query.toLowerCase().includes('transaction') && matchTxCmd) {
      const txId = parseInt(matchTxCmd[1], 10);
      handleRedirectToTransaction(txId);
      setPrompt('');
      return;
    }

    setPrompt('');
    setLoading(true);

    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const userMessage = { role: 'user', text: query, time: timeString };
    const initialAgentMessage = {
      role: 'assistant',
      text: '',
      steps: [],
      approvalNeeded: null,
      status: 'thinking',
      time: timeString
    };

    setMessages((prev) => [...prev, userMessage, initialAgentMessage]);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/run-stream?prompt=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.replace('data: ', ''));

              setMessages((prev) => {
                const updated = [...prev];
                const currentMsg = updated[updated.length - 1];

                if (data.event_type === 'APPROVAL_REQUIRED') {
                  currentMsg.approvalNeeded = data.payload;
                  currentMsg.status = 'awaiting_approval';
                } else if (data.event_type === 'FINAL_ANSWER') {
                  currentMsg.text = data.message;
                  currentMsg.status = 'complete';
                  fetchTransactions(); // Auto-refresh transaction history
                } else {
                  currentMsg.status = 'executing';
                  currentMsg.steps.push({
                    type: data.event_type,
                    title: data.title || data.event_type,
                    payload: data.payload
                  });
                }
                return updated;
              });
            } catch (e) {
              console.error('SSE JSON parse error:', e);
            }
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        const currentMsg = updated[updated.length - 1];
        currentMsg.text = '⚠️ Connection error. Please verify backend server is running on port 8000.';
        currentMsg.status = 'error';
        return updated;
      });
    } finally {
      setLoading(false);
      fetchTransactions();
    }
  };

  const handleApproval = async (approved, payload, messageIndex) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          invoice_number: payload.invoice_number,
          vendor_name: payload.vendor_name,
          amount: payload.amount,
          due_date: payload.due_date,
          email_date: payload.email_date,
          file_location: payload.file_location,
          approved: approved
        })
      });

      const data = await res.json();
      fetchTransactions();

      setMessages((prev) => {
        const updated = [...prev];
        const currentMsg = updated[messageIndex];
        currentMsg.approvalNeeded = null;
        currentMsg.status = 'complete';
        currentMsg.text = approved
          ? `✅ **Approved & Recorded in Ledger**\n- **Invoice:** #${payload.invoice_number}\n- **Vendor:** ${payload.vendor_name}\n- **Amount:** $${payload.amount?.toLocaleString()}\n- **Source File:** \`${payload.file_location}\`\n- **Transaction ID:** #${data.recorded_db_id}\n\n---ACTION_BUTTONS---\n[{"label": "View Transaction #${data.recorded_db_id}", "command": "View transaction history details for ID ${data.recorded_db_id}"}, {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}]`
          : `❌ **Transaction Rejected**\n- **Invoice:** #${payload.invoice_number}\n- **Vendor:** ${payload.vendor_name}\n\n---ACTION_BUTTONS---\n[{"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}]`;
        return updated;
      });
    } catch (err) {
      console.error('Approval submission error:', err);
    }
  };

  return (
    <div className="app-layout">
      {/* Transaction History Sidebar (Replaces Chat History) */}
      <aside className={`sidebar ${!sidebarOpen ? 'closed' : ''}`}>
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="sidebar-toggle-btn">
              ☰
            </button>
            {sidebarOpen && <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#8e918f' }}>TRANSACTION HISTORY</span>}
          </div>

          {sidebarOpen && (
            <>
              <button onClick={() => { setSelectedTx(null); setMessages([]); }} className="new-thread-btn" style={{ marginBottom: '16px' }}>
                + New Task Execution
              </button>

              <div className="transaction-history-list" style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {transactions.length === 0 ? (
                  <div style={{ fontSize: '0.75rem', color: '#8e918f', textAlign: 'center', marginTop: '20px' }}>
                    No recorded transactions in ledger
                  </div>
                ) : (
                  transactions.map((tx) => (
                    <div
                      key={tx.id}
                      onClick={() => handleRedirectToTransaction(tx.id)}
                      className={`tx-history-item ${selectedTx?.id === tx.id ? 'active' : ''}`}
                      style={{
                        padding: '10px 12px',
                        borderRadius: '10px',
                        backgroundColor: selectedTx?.id === tx.id ? '#282a2c' : '#131314',
                        border: '1px solid #282a2c',
                        cursor: 'pointer',
                        fontSize: '0.78rem'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600, color: '#e3e3e3' }}>
                        <span>Tx #{tx.id} • {tx.vendor_name}</span>
                        <span style={{ color: '#10b981' }}>${tx.amount?.toLocaleString()}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8e918f', fontSize: '0.7rem', marginTop: '4px' }}>
                        <span>Invoice: {tx.invoice_number}</span>
                        <span>{tx.status || 'RECORDED'}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="main-content">
        <header className="top-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ color: '#4285f4', fontSize: '1.2rem' }}>✦</span>
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>WorkPilot Ledger Workspace</span>
          </div>
          <span className="brand-badge">sqlite3 // data/workpilot.db</span>
        </header>

        {/* Focused Single Transaction Redirection View */}
        {selectedTx ? (
          <div className="chat-feed" style={{ padding: '24px', maxWidth: '820px', margin: '0 auto', width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ color: '#4285f4', fontSize: '1.2rem' }}>📊 Transaction Record #{selectedTx.id}</h2>
              <button
                onClick={() => setSelectedTx(null)}
                style={{ background: '#1e1f20', border: '1px solid #282a2c', color: '#e3e3e3', padding: '6px 12px', borderRadius: '12px', cursor: 'pointer', fontSize: '0.8rem' }}
              >
                ← Return to Live Task Execution
              </button>
            </div>

            <div style={{ backgroundColor: '#1e1f20', border: '1px solid #282a2c', borderRadius: '16px', padding: '20px', lineHeight: '1.8' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '0.88rem' }}>
                <div><strong>Transaction ID:</strong> #{selectedTx.id}</div>
                <div><strong>Status:</strong> <span style={{ color: '#10b981' }}>{selectedTx.status}</span></div>
                <div><strong>Invoice Number:</strong> {selectedTx.invoice_number}</div>
                <div><strong>Vendor Name:</strong> {selectedTx.vendor_name}</div>
                <div><strong>Amount:</strong> ${selectedTx.amount?.toLocaleString()}</div>
                <div><strong>Due Date:</strong> {selectedTx.due_date}</div>
                <div style={{ gridColumn: 'span 2' }}><strong>Source PDF Location:</strong> <code style={{ color: '#fcd34d' }}>{selectedTx.file_location}</code></div>
                <div style={{ gridColumn: 'span 2' }}><strong>Recorded Timestamp:</strong> {selectedTx.created_at}</div>
              </div>

              <div className="action-buttons-wrapper" style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #282a2c' }}>
                <div className="action-buttons-label">✦ Transaction Actions:</div>
                <div className="action-buttons-grid">
                  <button className="decision-tree-btn" onClick={() => handleSendPrompt("Scan inbox for next invoice")}>
                    Scan Next Inbox Invoice →
                  </button>
                  <button className="decision-tree-btn" onClick={() => setSelectedTx(null)}>
                    Close Transaction View →
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Live Chat & Execution Stream */
          <div className="chat-feed">
            {messages.length === 0 ? (
              <div className="welcome-container">
                <div>
                  <h1 className="gemini-title">Hello, Financial Lead</h1>
                  <p style={{ color: '#8e918f', marginTop: '6px', fontSize: '0.9rem' }}>
                    How can WorkPilot assist with your transaction ledger processing today?
                  </p>
                </div>

                <div className="info-banner">
                  <strong>Transaction Redirection Enabled:</strong> If an invoice is already in the ledger, WorkPilot returns a redirect button linking directly to its Transaction ID.
                </div>

                <div className="prompt-grid">
                  {[
                    { title: 'Check ABC Corp Invoice', desc: 'Auto-detects existing record & returns View Transaction button', query: 'Scan inbox for ABC Corp and process the invoice.' },
                    { title: 'Test High-Value Approval', desc: 'Triggers safety gate with Approve & Record buttons ($12,500)', query: 'Scan inbox for Acme Supplies and process the invoice.' },
                    { title: 'Check Duplicate Status', desc: 'Queries database and offers direct transaction redirect', query: 'Scan inbox for ABC Corp to test duplicate check.' },
                    { title: 'Scan Utility Billing', desc: 'Parse Apex Cloud Services utility invoices', query: 'Scan inbox for Apex Cloud Services and check database status.' }
                  ].map((item, i) => (
                    <button key={i} className="prompt-card" onClick={() => handleSendPrompt(item.query)}>
                      <div className="prompt-card-title">{item.title}</div>
                      <div className="prompt-card-desc">{item.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`message-row ${msg.role}`}>
                  {msg.role === 'assistant' && <div className="avatar">✦</div>}

                  <div className="message-body">
                    <div className="message-bubble">
                      {/* Thought Chain Accordion */}
                      {msg.steps && msg.steps.length > 0 && (
                        <div className="thought-chain">
                          <button className="thought-header" onClick={() => toggleThoughtChain(idx)}>
                            <span>⚙️ Thought Chain ({msg.steps.length} actions)</span>
                            <span>{showThoughtChain[idx] ? '▲' : '▼'}</span>
                          </button>
                          {showThoughtChain[idx] && (
                            <div className="thought-content">
                              {msg.steps.map((s, sIdx) => (
                                <div key={sIdx} style={{ marginBottom: '8px', borderBottom: '1px solid #282a2c', paddingBottom: '6px' }}>
                                  › <strong>{s.title}</strong>
                                  {s.payload && (
                                    <pre style={{ fontSize: '0.7rem', color: '#8e918f', marginTop: '4px', overflowX: 'auto' }}>
                                      {JSON.stringify(s.payload, null, 2)}
                                    </pre>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Human Safety Approval Required Card */}
                      {msg.approvalNeeded && (
                        <div className="approval-card">
                          <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>⚠️ Human Safety Approval Required</div>
                          <p style={{ marginTop: '6px', lineHeight: '1.4' }}>
                            Invoice <strong>#{msg.approvalNeeded.invoice_number}</strong> from <strong>{msg.approvalNeeded.vendor_name}</strong> totals <strong>${msg.approvalNeeded.amount?.toLocaleString()}</strong> (Exceeds $10,000 Safety Threshold).
                          </p>
                          <div style={{ marginTop: '6px', fontSize: '0.75rem', color: '#fcd34d' }}>
                            <div>📁 <strong>Source Attachment:</strong> {msg.approvalNeeded.file_location}</div>
                            <div>🗄️ <strong>Target Ledger:</strong> {msg.approvalNeeded.target_db_location}</div>
                          </div>
                          <div className="approval-buttons">
                            <button className="btn-approve" onClick={() => handleApproval(true, msg.approvalNeeded, idx)}>
                              Approve & Store in Ledger
                            </button>
                            <button className="btn-reject" onClick={() => handleApproval(false, msg.approvalNeeded, idx)}>
                              Reject Transaction
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Output Text & Interactive Decision Buttons */}
                      {msg.text ? (
                        (() => {
                          const { bodyText, actionButtons } = parseMessageContent(msg.text);
                          return (
                            <div className="message-content-wrapper">
                              <div className="message-text">{bodyText}</div>

                              {/* Decision / Redirect Buttons */}
                              {actionButtons.length > 0 && (
                                <div className="action-buttons-wrapper">
                                  <div className="action-buttons-label">✦ Select Next Action:</div>
                                  <div className="action-buttons-grid">
                                    {actionButtons.map((btn, bIdx) => (
                                      <button
                                        key={bIdx}
                                        className="decision-tree-btn"
                                        onClick={() => handleSendPrompt(btn.command)}
                                        disabled={loading}
                                      >
                                        {btn.label} <span className="btn-arrow">→</span>
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()
                      ) : (
                        msg.status === 'thinking' && 'Scanning inbox & checking transaction ledger...'
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Footer Input Bar */}
        <footer className="input-footer">
          <form
            className="input-pill"
            onSubmit={(e) => {
              e.preventDefault();
              handleSendPrompt();
            }}
          >
            <span style={{ color: '#4285f4' }}>✦</span>
            <input
              type="text"
              className="input-field"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask WorkPilot or state invoice instruction..."
              disabled={loading}
            />
            <button type="submit" className="send-btn" disabled={loading || !prompt.trim()}>
              ↑
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}