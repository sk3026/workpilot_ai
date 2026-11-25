import React, { useState, useRef, useEffect } from 'react';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? window.location.origin : 'http://localhost:8000')).replace(/\/$/, '');

const PROMPTS = [
  { title: 'Check ABC Corp Invoice', desc: 'Auto-detects existing record & returns View Transaction button', query: 'Scan inbox for ABC Corp and process the invoice.' },
  { title: 'Test High-Value Approval', desc: 'Triggers safety gate with Approve & Record buttons ($12,500)', query: 'Scan inbox for Acme Supplies and process the invoice.' },
  { title: 'Check Duplicate Status', desc: 'Queries database and offers direct transaction redirect', query: 'Scan inbox for ABC Corp to test duplicate check.' },
  { title: 'Scan Utility Billing', desc: 'Parse Apex Cloud Services utility invoices', query: 'Scan inbox for Apex Cloud Services and check database status.' }
];

export default function WorkPilotChat() {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [transactions, setTransactions] = useState([]);
  const [deletingTxId, setDeletingTxId] = useState(null);
  const [selectedTx, setSelectedTx] = useState(null);
  const [showThoughtChain, setShowThoughtChain] = useState({});
  const messagesEndRef = useRef(null);

  const fetchTransactions = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/transactions`);
      if (res.ok) setTransactions(await res.json());
    } catch (err) {
      console.error('Failed to fetch transaction history:', err);
    }
  };

  const handleDeleteTransaction = async (e, txId) => {
    e.stopPropagation();
    if (!window.confirm(`Delete transaction #${txId}?`)) return;
    setDeletingTxId(txId);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/transactions/${txId}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Failed to delete transaction');
      setTransactions((prev) => prev.filter((tx) => tx.id !== txId));
      if (selectedTx?.id === txId) setSelectedTx(null);
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setDeletingTxId(null);
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

  const handleRedirectToTransaction = async (txId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/transactions/${txId}`);
      if (res.ok) setSelectedTx(await res.json());
    } catch (err) {
      console.error(`Failed to load transaction #${txId}:`, err);
    }
  };

  const parseMessageContent = (rawText) => {
    if (!rawText) return { bodyText: '', actionButtons: [] };
    if (rawText.includes('---ACTION_BUTTONS---')) {
      const [bodyPart, btnPart] = rawText.split('---ACTION_BUTTONS---');
      try {
        return { bodyText: bodyPart.trim(), actionButtons: JSON.parse(btnPart.trim()) };
      } catch {
        return { bodyText: bodyPart.trim(), actionButtons: [] };
      }
    }
    return { bodyText: rawText, actionButtons: [] };
  };

  const handleSendPrompt = async (textToSend) => {
    setSelectedTx(null);
    const query = (textToSend || prompt).trim();
    if (!query || loading) return;

    const matchTxCmd = query.match(/ID\s*(\d+)/i) || query.match(/#(\d+)/);
    if (query.toLowerCase().includes('transaction') && matchTxCmd) {
      handleRedirectToTransaction(parseInt(matchTxCmd[1], 10));
      setPrompt('');
      return;
    }

    setPrompt('');
    setLoading(true);

    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: query, time: timeString },
      { role: 'assistant', text: '', steps: [], approvalNeeded: null, status: 'thinking', time: timeString }
    ]);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/run-stream?prompt=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            setMessages((prev) => {
              const updated = [...prev];
              const currentMsg = { ...updated[updated.length - 1] };

              if (data.event_type === 'APPROVAL_REQUIRED') {
                currentMsg.approvalNeeded = data.payload;
                currentMsg.status = 'awaiting_approval';
              } else if (data.event_type === 'FINAL_ANSWER') {
                currentMsg.text = data.message;
                currentMsg.status = 'complete';
                fetchTransactions();
              } else {
                currentMsg.status = 'executing';
                currentMsg.steps = [
                  ...currentMsg.steps,
                  { type: data.event_type, title: data.title || data.event_type, payload: data.payload }
                ];
              }
              updated[updated.length - 1] = currentMsg;
              return updated;
            });
          } catch (e) {
            console.error('SSE JSON parse error:', e);
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          text: '⚠️ Connection error. Please verify backend server is running on port 8000.',
          status: 'error'
        };
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
          approved
        })
      });

      const data = await res.json();
      fetchTransactions();

      const text = approved
        ? `✅ **Approved & Recorded in Ledger**\n- **Invoice:** #${payload.invoice_number}\n- **Vendor:** ${payload.vendor_name}\n- **Amount:** $${payload.amount?.toLocaleString()}\n- **Source File:** \`${payload.file_location}\`\n- **Transaction ID:** #${data.recorded_db_id}\n\n---ACTION_BUTTONS---\n[{"label": "View Transaction #${data.recorded_db_id}", "command": "View transaction history details for ID ${data.recorded_db_id}"}, {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}]`
        : `❌ **Transaction Rejected**\n- **Invoice:** #${payload.invoice_number}\n- **Vendor:** ${payload.vendor_name}\n\n---ACTION_BUTTONS---\n[{"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}]`;

      setMessages((prev) =>
        prev.map((msg, idx) =>
          idx === messageIndex ? { ...msg, approvalNeeded: null, status: 'complete', text } : msg
        )
      );
    } catch (err) {
      console.error('Approval submission error:', err);
    }
  };

  return (
    <div className="app-layout">
      {/* Transaction History Sidebar */}
      <aside className={`sidebar ${!sidebarOpen ? 'closed' : ''}`}>
        <div className="sidebar-inner">
          <div className="sidebar-top">
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="sidebar-toggle-btn" title="Toggle Sidebar">
              ☰
            </button>
            {sidebarOpen && <span className="sidebar-label">TRANSACTION HISTORY</span>}
          </div>

          {sidebarOpen && (
            <>
              <button
                onClick={() => { setSelectedTx(null); setMessages([]); }}
                className="new-thread-btn"
              >
                + New Task Execution
              </button>

              <div className="transaction-history-list">
                {transactions.length === 0 ? (
                  <div className="empty-ledger">No recorded transactions in ledger</div>
                ) : (
                  transactions.map((tx) => (
                    <div
                      key={tx.id}
                      onClick={() => handleRedirectToTransaction(tx.id)}
                      className={`tx-history-item ${selectedTx?.id === tx.id ? 'active' : ''}`}
                    >
                      <div className="tx-item-top">
                        <span>Tx #{tx.id} • {tx.vendor_name}</span>
                        <div className="tx-item-actions">
                          <span className="tx-amount">${tx.amount?.toLocaleString()}</span>
                          <button
                            type="button"
                            title={`Delete transaction #${tx.id}`}
                            aria-label={`Delete transaction #${tx.id}`}
                            disabled={deletingTxId === tx.id}
                            onClick={(e) => handleDeleteTransaction(e, tx.id)}
                            className="tx-delete-btn"
                          >
                            {deletingTxId === tx.id ? '…' : '🗑'}
                          </button>
                        </div>
                      </div>
                      <div className="tx-item-bottom">
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
          <div className="brand-title">
            <span className="wp-badge">WP</span>
            <span>WorkPilot Ledger Workspace</span>
          </div>
          <span className="brand-badge">sqlite3 // data/workpilot.db</span>
        </header>

        {/* Focused Single Transaction View */}
        {selectedTx ? (
          <div className="chat-feed">
            <div className="tx-detail-header">
              <h2>Transaction Record #{selectedTx.id}</h2>
              <button onClick={() => setSelectedTx(null)} className="back-btn">
                ← Return to Live Task Execution
              </button>
            </div>

            <div className="tx-detail-card">
              <div className="tx-detail-grid">
                <div><strong>Transaction ID:</strong> #{selectedTx.id}</div>
                <div><strong>Status:</strong> <span className="tx-amount">{selectedTx.status}</span></div>
                <div><strong>Invoice Number:</strong> {selectedTx.invoice_number}</div>
                <div><strong>Vendor Name:</strong> {selectedTx.vendor_name}</div>
                <div><strong>Amount:</strong> ${selectedTx.amount?.toLocaleString()}</div>
                <div><strong>Due Date:</strong> {selectedTx.due_date}</div>
                <div className="span-2"><strong>Source PDF Location:</strong> <code className="code-path">{selectedTx.file_location}</code></div>
                <div className="span-2"><strong>Recorded Timestamp:</strong> {selectedTx.created_at}</div>
              </div>

              <div className="action-buttons-wrapper">
                <div className="action-buttons-label">› Transaction Actions:</div>
                <div className="action-buttons-grid">
                  <button className="decision-tree-btn" onClick={() => handleSendPrompt('Scan inbox for next invoice')}>
                    Scan Next Inbox Invoice <span className="btn-arrow">→</span>
                  </button>
                  <button className="decision-tree-btn" onClick={() => setSelectedTx(null)}>
                    Close Transaction View <span className="btn-arrow">→</span>
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
                  <h1 className="workspace-title">WorkPilot Ledger Agent</h1>
                  <p className="workspace-subtitle">
                    Automate invoice extraction, duplicate verification, and ledger commits.
                  </p>
                </div>

                <div className="prompt-grid">
                  {PROMPTS.map((item, i) => (
                    <button key={i} className="prompt-card" onClick={() => handleSendPrompt(item.query)}>
                      <div className="prompt-card-title">{item.title}</div>
                      <div className="prompt-card-desc">{item.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => {
                const { bodyText, actionButtons } = parseMessageContent(msg.text);
                return (
                  <div key={idx} className={`message-row ${msg.role}`}>
                    {msg.role === 'assistant' && <div className="avatar">WP</div>}

                    <div className="message-body">
                      <div className="message-bubble">
                        {/* Thought Chain Accordion */}
                        {msg.steps?.length > 0 && (
                          <div className="thought-chain">
                            <button className="thought-header" onClick={() => toggleThoughtChain(idx)}>
                              <span>⚙️ Thought Chain ({msg.steps.length} actions)</span>
                              <span>{showThoughtChain[idx] ? '▲' : '▼'}</span>
                            </button>
                            {showThoughtChain[idx] && (
                              <div className="thought-content">
                                {msg.steps.map((s, sIdx) => (
                                  <div key={sIdx} className="thought-step">
                                    › <strong>{s.title}</strong>
                                    {s.payload && (
                                      <pre className="thought-payload">
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
                            <div className="approval-title">⚠️ Human Safety Approval Required</div>
                            <p className="approval-desc">
                              Invoice <strong>#{msg.approvalNeeded.invoice_number}</strong> from <strong>{msg.approvalNeeded.vendor_name}</strong> totals <strong>${msg.approvalNeeded.amount?.toLocaleString()}</strong> (Exceeds $10,000 Safety Threshold).
                            </p>
                            <div className="approval-meta">
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
                          <div className="message-content-wrapper">
                            <div className="message-text">{bodyText}</div>

                            {actionButtons.length > 0 && (
                              <div className="action-buttons-wrapper">
                                <div className="action-buttons-label">› Select Next Action:</div>
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
                        ) : (
                          msg.status === 'thinking' && 'Scanning inbox & checking transaction ledger...'
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
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
            <span className="terminal-prompt">&gt;_</span>
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