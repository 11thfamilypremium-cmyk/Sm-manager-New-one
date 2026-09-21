// Customer Checkout Page Logic

function showCustomerToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

document.addEventListener('DOMContentLoaded', () => {
  const utrForm = document.getElementById('submit-utr-form');
  const utrInput = document.getElementById('utr-input');
  const btnSubmit = document.getElementById('btn-submit-utr');
  const approvedBox = document.getElementById('approved-box');
  const channelLink = document.getElementById('channel-invite-link');
  const utrSection = document.getElementById('utr-form-section');

  let pollInterval = null;

  function startPollingStatus() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/customer/status/${ORDER_ID}`);
        const data = await res.json();
        if (data.ok && data.status === 'active' && data.invite_link) {
          clearInterval(pollInterval);
          if (utrSection) utrSection.style.display = 'none';
          if (approvedBox && channelLink) {
            channelLink.href = data.invite_link;
            approvedBox.style.display = 'block';
            showCustomerToast('🎉 Your payment was approved! Click below to join the VIP Channel.', 'success');
          }
        }
      } catch (e) {
        // Silent polling error catch
      }
    }, 4000);
  }

  // If already pending approval, start polling
  if (CURRENT_STATUS === 'pending_approval') {
    startPollingStatus();
  }

  if (utrForm) {
    utrForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const utr = utrInput.value.trim();
      if (!utr || utr.length < 6) {
        showCustomerToast('Please enter a valid UPI UTR / Transaction ID (min 6-12 digits)', 'error');
        return;
      }

      btnSubmit.disabled = true;
      btnSubmit.innerText = 'Submitting...';

      try {
        const resp = await fetch(`/api/customer/submit-utr/${ORDER_ID}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ utr })
        });
        const data = await resp.json();

        if (data.ok) {
          showCustomerToast(data.message, 'success');
          utrSection.innerHTML = `
            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-sm); padding: 16px; margin-top: 16px;">
              <h4 style="color: var(--warning); margin-bottom: 6px;">UTR Submitted (${utr})</h4>
              <p style="font-size: 13px; color: var(--text-muted);">
                Verification in progress! Please keep this page open. As soon as admin approves, your VIP channel link will appear here.
              </p>
            </div>
          `;
          startPollingStatus();
        } else {
          showCustomerToast(data.error || 'Submission failed', 'error');
          btnSubmit.disabled = false;
          btnSubmit.innerText = 'Submit UTR for Verification';
        }
      } catch (err) {
        showCustomerToast('Network error submitting UTR', 'error');
        btnSubmit.disabled = false;
        btnSubmit.innerText = 'Submit UTR for Verification';
      }
    });
  }
});
