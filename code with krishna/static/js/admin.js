document.addEventListener('DOMContentLoaded', () => {
    loadMetrics();
    loadPendingPayments();
    loadCustomers();
    loadAuditLogs();

    // Refresh every 30 seconds
    setInterval(() => {
        loadMetrics();
        loadPendingPayments();
    }, 30000);
});

// Load Overview KPIs
async function loadMetrics() {
    try {
        const res = await fetch('/api/admin/metrics');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('kpi-total-customers').innerText = data.total_customers;
        document.getElementById('kpi-active-members').innerText = data.active_members;
        document.getElementById('kpi-expiring-soon').innerText = data.expiring_soon;
        document.getElementById('kpi-expired').innerText = data.expired_members;
        document.getElementById('kpi-pending-payments').innerText = data.pending_payments;
        document.getElementById('kpi-revenue').innerText = `₹${data.total_revenue.toFixed(2)}`;

        const pendingBadge = document.getElementById('pending-badge');
        if (pendingBadge) {
            pendingBadge.innerText = data.pending_payments;
            pendingBadge.style.display = data.pending_payments > 0 ? 'inline-block' : 'none';
        }

        // Sync Monitor
        const syncStatusEl = document.getElementById('sync-status-indicator');
        if (syncStatusEl) {
            if (data.sync_status.failed > 0) {
                syncStatusEl.innerHTML = `<span class="status-pill status-expired">⚠️ ${data.sync_status.failed} Sync Issues</span>`;
            } else {
                syncStatusEl.innerHTML = `<span class="status-pill status-active">✅ Synced</span>`;
            }
        }
    } catch (err) {
        console.error("Error loading metrics:", err);
    }
}

// Load Pending Payments Table
async function loadPendingPayments() {
    try {
        const res = await fetch('/api/admin/pending-payments');
        const data = await res.json();
        const tbody = document.getElementById('pending-payments-tbody');
        tbody.innerHTML = '';

        if (!data.pending_payments || data.pending_payments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-muted);">No pending payments at this time.</td></tr>';
            return;
        }

        data.pending_payments.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><b>${p.customer_name}</b><br><small style="color:var(--text-muted)">@${p.telegram_username || 'no_username'}</small></td>
                <td><code>${p.telegram_id}</code></td>
                <td><strong style="color:var(--success)">₹${p.amount.toFixed(2)}</strong></td>
                <td><code style="font-weight:700; color:#818cf8;">${p.utr || 'Pending'}</code></td>
                <td><small>${p.transaction_id}</small></td>
                <td>${p.created_at ? new Date(p.created_at).toLocaleString() : ''}</td>
                <td><span class="status-pill status-pending">${p.payment_status}</span></td>
                <td>
                    <button class="btn btn-success" style="padding: 4px 10px; font-size:12px;" onclick="approvePayment('${p.transaction_id}')">Approve</button>
                    <button class="btn btn-danger" style="padding: 4px 10px; font-size:12px;" onclick="rejectPaymentModal('${p.transaction_id}')">Reject</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading pending payments:", err);
    }
}

async function approvePayment(txnId) {
    if (!confirm("Are you sure you want to APPROVE this payment and activate VIP access?")) return;
    try {
        const res = await fetch('/api/admin/approve-payment', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({transaction_id: txnId})
        });
        const data = await res.json();
        if (res.ok) {
            alert("Payment Approved! Invite link generated and sent to customer via bot.");
            loadMetrics();
            loadPendingPayments();
            loadCustomers();
        } else {
            alert("Approval error: " + data.error);
        }
    } catch (err) {
        alert("Server error during approval");
    }
}

async function rejectPaymentModal(txnId) {
    const reason = prompt("Enter reason for rejection:", "UTR could not be verified.");
    if (reason === null) return;

    try {
        const res = await fetch('/api/admin/reject-payment', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({transaction_id: txnId, reason: reason})
        });
        const data = await res.json();
        if (res.ok) {
            alert("Payment Rejected. Rejection message sent to customer.");
            loadMetrics();
            loadPendingPayments();
        } else {
            alert("Rejection error: " + data.error);
        }
    } catch (err) {
        alert("Server error during rejection");
    }
}

// Load Customers Table
async function loadCustomers() {
    const search = document.getElementById('search-input')?.value || '';
    const filter = document.getElementById('filter-select')?.value || 'ALL';

    try {
        const res = await fetch(`/api/admin/customers?search=${encodeURIComponent(search)}&filter=${filter}`);
        const data = await res.json();
        const tbody = document.getElementById('customers-tbody');
        tbody.innerHTML = '';

        if (!data.customers || data.customers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color: var(--text-muted);">No customers found matching search/filter.</td></tr>';
            return;
        }

        data.customers.forEach(c => {
            const tr = document.createElement('tr');
            
            let statusBadge = '<span class="status-pill status-expired">EXPIRED</span>';
            if (c.subscription_status === 'ACTIVE') statusBadge = '<span class="status-pill status-active">ACTIVE</span>';
            if (c.subscription_status === 'EXPIRING_SOON') statusBadge = '<span class="status-pill status-expiring">EXPIRING SOON</span>';

            tr.innerHTML = `
                <td><b>${c.first_name || ''} ${c.last_name || ''}</b><br><small style="color:var(--text-muted)">@${c.username || 'N/A'}</small></td>
                <td><code>${c.telegram_id}</code></td>
                <td>₹${c.effective_price.toFixed(2)} ${c.custom_price ? '<small style="color:#818cf8;">(Custom)</small>' : ''}</td>
                <td>${statusBadge}</td>
                <td><b>${c.days_remaining} Days</b></td>
                <td><small>${c.membership_status}</small></td>
                <td>₹${c.total_paid.toFixed(2)}</td>
                <td>${c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}</td>
                <td>
                    <button class="btn btn-secondary" style="padding: 4px 10px; font-size:12px;" onclick="viewCustomerDetail('${c.id}')">Manage</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading customers:", err);
    }
}

// Customer Detail Modal
async function viewCustomerDetail(customerId) {
    try {
        const res = await fetch(`/api/admin/customer/${customerId}`);
        const c = await res.json();

        const modal = document.getElementById('customer-modal');
        const content = document.getElementById('customer-modal-content');

        content.innerHTML = `
            <h3>Customer Profile: ${c.first_name || ''} ${c.last_name || ''} (@${c.username || 'no_username'})</h3>
            <p style="color:var(--text-muted); margin-bottom:16px;">Telegram ID: <code>${c.telegram_id}</code> | Configured Price: <strong>₹${c.effective_price}</strong></p>

            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px;">
                <button class="btn btn-primary" onclick="setCustomPrice('${c.id}', ${c.effective_price})">Set Custom Price</button>
                <button class="btn btn-success" onclick="adjustExpiry('${c.id}')">Extend Expiry (+Days)</button>
                <button class="btn btn-secondary" onclick="generateInviteLink('${c.id}')">Generate & Send Invite</button>
                <button class="btn btn-danger" onclick="kickMember('${c.id}')">Remove Member from Channel</button>
            </div>

            <h4 style="margin-top:20px;">Subscriptions History</h4>
            <table style="margin-bottom:20px;">
                <thead><tr><th>Plan</th><th>Amount</th><th>Start Date</th><th>Expiry Date</th><th>Status</th></tr></thead>
                <tbody>
                    ${(c.subscriptions || []).map(s => `
                        <tr>
                            <td>${s.plan_name}</td>
                            <td>₹${s.amount}</td>
                            <td>${new Date(s.start_date).toLocaleDateString()}</td>
                            <td>${new Date(s.expiry_date).toLocaleDateString()}</td>
                            <td>${s.status}</td>
                        </tr>
                    `).join('') || '<tr><td colspan="5">No subscriptions.</td></tr>'}
                </tbody>
            </table>

            <h4>Transactions History</h4>
            <table>
                <thead><tr><th>Txn ID</th><th>Amount</th><th>UTR</th><th>Status</th><th>Submitted At</th></tr></thead>
                <tbody>
                    ${(c.transactions || []).map(t => `
                        <tr>
                            <td>${t.transaction_id}</td>
                            <td>₹${t.amount}</td>
                            <td><code>${t.utr || 'N/A'}</code></td>
                            <td>${t.payment_status}</td>
                            <td>${t.submitted_at ? new Date(t.submitted_at).toLocaleString() : ''}</td>
                        </tr>
                    `).join('') || '<tr><td colspan="5">No transactions.</td></tr>'}
                </tbody>
            </table>
        `;

        modal.style.display = 'flex';
    } catch (err) {
        alert("Error loading customer detail");
    }
}

function closeModal() {
    document.getElementById('customer-modal').style.display = 'none';
}

async function setCustomPrice(customerId, currentPrice) {
    const p = prompt("Enter customer-specific price (₹):", currentPrice);
    if (p === null) return;

    try {
        const res = await fetch(`/api/admin/customer/${customerId}/custom-price`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({price: parseFloat(p)})
        });
        if (res.ok) {
            alert("Custom price updated!");
            closeModal();
            loadCustomers();
        }
    } catch (err) {
        alert("Error setting custom price");
    }
}

async function adjustExpiry(customerId) {
    const days = prompt("Enter number of days to extend (+30, +10, etc.):", "30");
    if (days === null) return;
    const reason = prompt("Enter reason for extension:", "Compensation / Support extension");

    try {
        const res = await fetch(`/api/admin/customer/${customerId}/adjust-expiry`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({days: parseInt(days), reason: reason})
        });
        if (res.ok) {
            alert("Subscription extended!");
            closeModal();
            loadCustomers();
        }
    } catch (err) {
        alert("Error extending expiry");
    }
}

async function generateInviteLink(customerId) {
    try {
        const res = await fetch(`/api/admin/customer/${customerId}/generate-invite`, {method: 'POST'});
        const data = await res.json();
        if (res.ok) {
            alert("New single-use invite generated and sent to customer via Telegram bot!");
            closeModal();
        }
    } catch (err) {
        alert("Error generating invite link");
    }
}

async function kickMember(customerId) {
    if (!confirm("Are you sure you want to remove this member from the VIP channel?")) return;
    try {
        const res = await fetch(`/api/admin/customer/${customerId}/remove-member`, {method: 'POST'});
        if (res.ok) {
            alert("Member removed from Telegram VIP channel.");
            closeModal();
            loadCustomers();
        }
    } catch (err) {
        alert("Error removing member");
    }
}

// Trigger Google Sheets Rebuild
async function rebuildGoogleSheets() {
    if (!confirm("Are you sure you want to REBUILD Google Sheets from PostgreSQL database?")) return;
    try {
        const res = await fetch('/api/admin/rebuild-sheets', {method: 'POST'});
        const data = await res.json();
        if (res.ok) {
            alert("Google Sheets Rebuild process completed successfully!");
            loadMetrics();
        } else {
            alert("Rebuild failed: " + data.error);
        }
    } catch (err) {
        alert("Error rebuilding Google Sheets");
    }
}

// Load Audit Logs
async function loadAuditLogs() {
    try {
        const res = await fetch('/api/admin/audit-logs');
        const data = await res.json();
        const tbody = document.getElementById('audit-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        data.audit_logs.forEach(l => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><small>${l.timestamp ? new Date(l.timestamp).toLocaleString() : ''}</small></td>
                <td><b>${l.actor}</b></td>
                <td><code>${l.action}</code></td>
                <td>${l.details || ''}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading audit logs:", err);
    }
}

function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).style.display = 'block';
    document.getElementById(`nav-${tabName}`).classList.add('active');
}
