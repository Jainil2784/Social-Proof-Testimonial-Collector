// Main JS - Testimonial & Social Proof Collector
// Modules 0, 1, 2 — Foundation + MongoDB + Auth
const API_BASE_URL = (window.location.protocol.startsWith('http') && window.location.port === '8000')
    ? `${window.location.protocol}//${window.location.host}`
    : 'http://127.0.0.1:8000';

// Bootstrap modal instances (lazy-init)
let _authModal = null;
let _verifyModal = null;
let _forgotModal = null;
let _profileModal = null;

function getModal(id) {
    return bootstrap.Modal.getOrCreateInstance(document.getElementById(id));
}

// Active reset token when visiting ?auth=reset&token=...
let _activeResetToken = null;

// ─── APP INIT ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    restoreAuthState();
    // Auto-open auth modals based on URL query parameter ?auth=...
    const params = new URLSearchParams(window.location.search);
    const authParam = params.get('auth');
    const queryToken = params.get('token');

    if (authParam === 'login') {
        setTimeout(() => showAuthModal('login'), 350);
    } else if (authParam === 'register') {
        setTimeout(() => showAuthModal('register'), 350);
    } else if (authParam === 'forgot') {
        setTimeout(() => showForgotModal(), 350);
    } else if (authParam === 'reset') {
        if (queryToken) _activeResetToken = queryToken;
        setTimeout(() => showResetStep(), 350);
    } else if (authParam === 'verify') {
        setTimeout(() => handleVerificationLink(queryToken), 350);
    }
});


// ─── HEALTH CHECK ────────────────────────────────────────────────────────────
async function checkHealth() {
    const statusContainer = document.getElementById('status-container');
    const systemHealthBadge = document.getElementById('system-health-badge');
    const navStatusText = document.getElementById('nav-status-text');
    const navStatusIndicator = document.getElementById('nav-status-indicator');

    const startTime = performance.now();

    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        const endTime = performance.now();
        const responseTimeMs = Math.round(endTime - startTime);

        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();

        if (navStatusText) navStatusText.textContent = 'Backend Active';
        if (navStatusIndicator) {
            const dot = navStatusIndicator.querySelector('.status-dot');
            if (dot) dot.className = 'status-dot active';
            navStatusIndicator.style.backgroundColor = 'rgba(209, 250, 229, 0.8)';
            navStatusIndicator.style.borderColor = '#a7f3d0';
            navStatusIndicator.style.color = '#065f46';
        }

        if (systemHealthBadge) {
            systemHealthBadge.className = 'badge bg-emerald text-white border-0 px-3 py-2 rounded-pill fw-semibold fs-7 shadow-sm';
            systemHealthBadge.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> All Systems Operational';
        }

        if (statusContainer) {
            statusContainer.innerHTML = `
                <div class="alert border-0 bg-emerald-light text-dark p-4 rounded-3 mb-0 shadow-sm" role="alert">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-3">
                        <div class="d-flex align-items-center gap-3">
                            <span class="bg-emerald text-white rounded-circle p-2.5 d-flex shadow-sm">
                                <i class="bi bi-check-lg fs-4"></i>
                            </span>
                            <div>
                                <h6 class="mb-1 fw-bold text-dark fs-6">All Services Online &amp; Operational</h6>
                                <small class="text-secondary fs-7">
                                    System response time: <strong class="text-emerald">${responseTimeMs}ms</strong> • Status: <strong class="text-emerald">${data.status.toUpperCase()}</strong>
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        if (navStatusText) navStatusText.textContent = 'Service Offline';
        if (navStatusIndicator) {
            const dot = navStatusIndicator.querySelector('.status-dot');
            if (dot) dot.className = 'status-dot error';
            navStatusIndicator.style.backgroundColor = 'rgba(254, 226, 226, 0.8)';
            navStatusIndicator.style.borderColor = '#fca5a5';
            navStatusIndicator.style.color = '#991b1b';
        }
        if (systemHealthBadge) {
            systemHealthBadge.className = 'badge bg-danger text-white border-0 px-3 py-2 rounded-pill fw-semibold fs-7';
            systemHealthBadge.innerHTML = '<i class="bi bi-x-circle-fill me-1"></i> Service Disconnected';
        }
        if (statusContainer) {
            statusContainer.innerHTML = `
                <div class="alert border-0 bg-danger-subtle text-dark p-4 rounded-3 mb-0" role="alert">
                    <div class="d-flex align-items-center gap-3">
                        <span class="bg-danger text-white rounded-circle p-2.5 d-flex shadow-sm">
                            <i class="bi bi-exclamation-triangle-fill fs-4"></i>
                        </span>
                        <div>
                            <h6 class="mb-1 fw-bold text-dark fs-6">Service Temporarily Unavailable</h6>
                            <small class="text-secondary fs-7">
                                Unable to connect to platform services. Please check server availability.
                            </small>
                        </div>
                    </div>
                </div>
            `;
        }
        console.error('Health check failed:', error);
    }
}

// ─── AUTH STATE ──────────────────────────────────────────────────────────────
async function restoreAuthState() {
    // Try /me silently to see if user is already logged in via cookie
    try {
        let res = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: 'include' });
        if (res.status === 401) {
            // Attempt token refresh via HTTP-only refresh token cookie
            const refreshRes = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
                method: 'POST',
                credentials: 'include'
            });
            if (refreshRes.ok) {
                res = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: 'include' });
            }
        }
        if (res.ok) {
            const data = await res.json();
            setNavLoggedIn(data.name);
        } else {
            setNavLoggedOut();
        }
    } catch (_) {
        setNavLoggedOut();
    }
}

function setNavLoggedIn(name) {
    document.getElementById('auth-nav-buttons').classList.add('d-none');
    document.getElementById('auth-user-pill').classList.remove('d-none');
    document.getElementById('nav-user-name').textContent = name;
    
    const spacesNav = document.getElementById('nav-item-spaces');
    if (spacesNav) spacesNav.classList.remove('d-none');

    const spacesSec = document.getElementById('spaces-section');
    if (spacesSec) {
        spacesSec.classList.remove('d-none');
        fetchOwnerSpaces();
    }
}

function setNavLoggedOut() {
    document.getElementById('auth-nav-buttons').classList.remove('d-none');
    document.getElementById('auth-user-pill').classList.add('d-none');

    const spacesNav = document.getElementById('nav-item-spaces');
    if (spacesNav) spacesNav.classList.add('d-none');

    const spacesSec = document.getElementById('spaces-section');
    if (spacesSec) spacesSec.classList.add('d-none');
}

// ─── MODAL HELPERS ───────────────────────────────────────────────────────────
function showAuthModal(tab = 'login') {
    switchAuthTab(tab);
    clearAuthAlert();
    getModal('authModal').show();
}

function switchAuthTab(tab) {
    const loginForm = document.getElementById('form-login');
    const registerForm = document.getElementById('form-register');
    const registerVerifyStep = document.getElementById('register-verify-step');
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');

    if (tab === 'login') {
        if (loginForm) loginForm.classList.remove('d-none');
        if (registerForm) registerForm.classList.add('d-none');
        if (registerVerifyStep) registerVerifyStep.classList.add('d-none');
        if (tabLogin) tabLogin.classList.add('active');
        if (tabRegister) tabRegister.classList.remove('active');
    } else {
        if (loginForm) loginForm.classList.add('d-none');
        if (registerForm) registerForm.classList.remove('d-none');
        if (registerVerifyStep) registerVerifyStep.classList.add('d-none');
        if (tabLogin) tabLogin.classList.remove('active');
        if (tabRegister) tabRegister.classList.add('active');
    }
    clearAuthAlert();
}

function showForgotModal() {
    getModal('authModal').hide();
    clearAlert('forgot-alert');
    const reqStep = document.getElementById('forgot-step-request');
    const resetStep = document.getElementById('forgot-step-reset');
    if (reqStep) reqStep.classList.remove('d-none');
    if (resetStep) resetStep.classList.add('d-none');
    setTimeout(() => getModal('forgotModal').show(), 300);
}

function showResetStep() {
    getModal('authModal').hide();
    clearAlert('forgot-alert');
    const reqStep = document.getElementById('forgot-step-request');
    const resetStep = document.getElementById('forgot-step-reset');
    if (!_activeResetToken) {
        if (reqStep) reqStep.classList.remove('d-none');
        if (resetStep) resetStep.classList.add('d-none');
        showAlert('forgot-alert', 'Reset link missing or expired. Please enter your email below to request a new link.', 'warning');
    } else {
        if (reqStep) reqStep.classList.add('d-none');
        if (resetStep) resetStep.classList.remove('d-none');
    }
    setTimeout(() => getModal('forgotModal').show(), 300);
}

function showVerifyModal() {
    getModal('profileModal').hide();
    getModal('authModal').hide();
    clearAlert('verify-alert');
    handleVerificationLink(null);
}

function showAlert(containerId, message, type = 'danger') {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.className = `alert alert-${type} rounded-3 fs-7 py-2 px-3`;
    el.innerHTML = message;
}

function clearAlert(containerId) {
    const el = document.getElementById(containerId);
    if (el) { el.className = 'd-none'; el.innerHTML = ''; }
}

function clearAuthAlert() { clearAlert('auth-alert'); }

// ─── REGISTER ────────────────────────────────────────────────────────────────
async function doRegister() {
    const name = document.getElementById('register-name').value.trim();
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value;

    if (!name || !email || !password) {
        return showAlert('auth-alert', 'Please fill in all fields.');
    }
    if (password.length < 8) {
        return showAlert('auth-alert', 'Password must be at least 8 characters.');
    }
    if (!email.toLowerCase().endsWith('@gmail.com')) {
        return showAlert('auth-alert', 'Only Gmail addresses (@gmail.com) are supported.');
    }

    const btn = document.getElementById('btn-register-submit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span> Creating Account...`;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name, email, password })
        });
        const data = await res.json();

        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-person-check me-1"></i> Create Account`;
        }

        if (!res.ok) {
            return showAlert('auth-alert', data.detail || 'Registration failed.');
        }

        // Clear input values
        document.getElementById('register-password').value = '';

        // Transition from form to email verification sent step
        const registerForm = document.getElementById('form-register');
        const registerVerifyStep = document.getElementById('register-verify-step');
        if (registerForm && registerVerifyStep) {
            registerForm.classList.add('d-none');
            registerVerifyStep.classList.remove('d-none');
            clearAlert('reg-step-alert');

            const stepIcon = document.getElementById('reg-step-icon');
            const stepTitle = document.getElementById('reg-step-title');
            const stepDesc = document.getElementById('reg-step-desc');
            const stepBadge = document.getElementById('reg-step-badge');

            const msgLower = (data.message || '').toLowerCase();
            const isDevConsole = data.message === 'dev_console';
            const isUnconfigured = !isDevConsole && (msgLower.includes('not configured') || msgLower.includes('email service is not configured'));
            const isError = !isDevConsole && !isUnconfigured && (msgLower.includes('unable to send') || msgLower.includes('could not be sent'));

            if (isDevConsole) {
                // Dev console mode — link printed to server terminal
                if (stepIcon) {
                    stepIcon.className = 'rounded-circle bg-warning-subtle text-warning mx-auto mb-3 d-flex align-items-center justify-content-center shadow-sm';
                    stepIcon.innerHTML = '<i class="bi bi-terminal-fill fs-2"></i>';
                }
                if (stepBadge) {
                    stepBadge.className = 'badge bg-warning text-dark px-3 py-1 rounded-pill';
                    stepBadge.innerHTML = '<i class="bi bi-clock-history me-1"></i> Email Verification Required';
                }
                if (stepTitle) stepTitle.textContent = 'Check the Server Terminal';
                if (stepDesc) stepDesc.textContent = "Your account has been created. Since SMTP is not configured, the verification link has been printed to the server terminal (uvicorn logs). Copy the link and open it in your browser to verify your email.";
                clearAlert('reg-step-alert');
            } else if (isUnconfigured) {
                // SMTP not configured and console mode also not available
                if (stepIcon) {
                    stepIcon.className = 'rounded-circle bg-danger-subtle text-danger mx-auto mb-3 d-flex align-items-center justify-content-center shadow-sm';
                    stepIcon.innerHTML = '<i class="bi bi-exclamation-octagon-fill fs-2"></i>';
                }
                if (stepBadge) {
                    stepBadge.className = 'badge bg-danger text-white px-3 py-1 rounded-pill';
                    stepBadge.innerHTML = '<i class="bi bi-x-circle me-1"></i> Email Verification Pending';
                }
                if (stepTitle) stepTitle.textContent = 'Email Verification Pending';
                if (stepDesc) stepDesc.textContent = "We couldn't send your verification email because the email service is not configured. Please contact the administrator or configure the email service.";
                showAlert('reg-step-alert', data.message || 'Email service is not configured.', 'warning');
            } else if (isError) {
                // Error during sending (e.g. auth failed)
                if (stepIcon) {
                    stepIcon.className = 'rounded-circle bg-danger-subtle text-danger mx-auto mb-3 d-flex align-items-center justify-content-center shadow-sm';
                    stepIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill fs-2"></i>';
                }
                if (stepBadge) {
                    stepBadge.className = 'badge bg-danger text-white px-3 py-1 rounded-pill';
                    stepBadge.innerHTML = '<i class="bi bi-x-circle me-1"></i> Email Verification Pending';
                }
                if (stepTitle) stepTitle.textContent = 'Email Verification Pending';
                if (stepDesc) stepDesc.textContent = data.message || 'Unable to send verification email. Please try again later.';
                showAlert('reg-step-alert', data.message, 'warning');
            } else {
                // Real SMTP configured and email successfully sent
                if (stepIcon) {
                    stepIcon.className = 'rounded-circle bg-warning-subtle text-warning mx-auto mb-3 d-flex align-items-center justify-content-center shadow-sm';
                    stepIcon.innerHTML = '<i class="bi bi-envelope-paper-heart-fill fs-2"></i>';
                }
                if (stepBadge) {
                    stepBadge.className = 'badge bg-warning text-dark px-3 py-1 rounded-pill';
                    stepBadge.innerHTML = '<i class="bi bi-clock-history me-1"></i> Email Verification Required';
                }
                if (stepTitle) stepTitle.textContent = 'Email Verification Required';
                if (stepDesc) stepDesc.textContent = "Your account has been created. We've sent a verification link to your email address. Please check your inbox and click the link to verify your account.";
                clearAlert('reg-step-alert');
            }
        }
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-person-check me-1"></i> Create Account`;
        }
        showAlert('auth-alert', 'Network error. Is the server running?');
    }
}

// ─── LOGIN ───────────────────────────────────────────────────────────────────
async function doLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    if (!email || !password) {
        return showAlert('auth-alert', 'Please fill in all fields.');
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (!res.ok) {
            return showAlert('auth-alert', data.detail || 'Login failed.');
        }

        // Login succeeded — navigate to the authenticated dashboard.
        window.location.href = '/dashboard';
    } catch (err) {
        showAlert('auth-alert', 'Network error. Is the server running?');
    }
}

// ─── REAL EMAIL VERIFICATION LINK HANDLER ────────────────────────────────────
async function handleVerificationLink(token) {
    getModal('profileModal').hide();
    getModal('authModal').hide();
    clearAlert('verify-alert');
    const modalTitle = document.getElementById('verify-modal-title');
    const modalDesc = document.getElementById('verify-modal-desc');
    const modalActions = document.getElementById('verify-modal-actions');
    const modalIcon = document.getElementById('verify-modal-icon');

    if (!token) {
        if (modalTitle) modalTitle.textContent = 'Verification Link Missing';
        if (modalDesc) modalDesc.textContent = 'No verification token was found in the link. Please check the email sent to your Gmail inbox.';
        if (modalIcon) {
            modalIcon.className = 'rounded-circle bg-warning-subtle text-warning mx-auto mb-3 mt-2 d-flex align-items-center justify-content-center shadow-sm';
            modalIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill fs-2"></i>';
        }
        showAlert('verify-alert', 'Missing verification token. Please open the link from your Gmail inbox.', 'warning');
        if (modalActions) {
            modalActions.innerHTML = `
                <button class="btn btn-outline-secondary w-100 py-2.5 fw-semibold rounded-3" onclick="switchToLoginAfterVerify()">
                    <i class="bi bi-box-arrow-in-right me-1"></i> Continue to Sign In
                </button>
            `;
        }
        getModal('verifyModal').show();
        return;
    }

    // Token present — validating with backend
    if (modalTitle) modalTitle.textContent = 'Verifying Email Address...';
    if (modalDesc) modalDesc.textContent = 'Contacting server to verify your email address...';
    if (modalIcon) {
        modalIcon.className = 'rounded-circle bg-emerald-subtle text-emerald mx-auto mb-3 mt-2 d-flex align-items-center justify-content-center shadow-sm';
        modalIcon.innerHTML = '<div class="spinner-border text-emerald" role="status"></div>';
    }
    if (modalActions) modalActions.innerHTML = '';
    getModal('verifyModal').show();

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/verify-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ token })
        });
        const data = await res.json();

        if (!res.ok) {
            const detailMsg = data.detail || 'Verification failed.';
            if (modalIcon) {
                modalIcon.className = 'rounded-circle bg-warning-subtle text-warning mx-auto mb-3 mt-2 d-flex align-items-center justify-content-center shadow-sm';
                modalIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill fs-2"></i>';
            }
            if (detailMsg.toLowerCase().includes('already verified')) {
                if (modalTitle) modalTitle.textContent = 'Already Verified';
                if (modalDesc) modalDesc.textContent = 'Your email address is already verified. You can sign in directly.';
                showAlert('verify-alert', '<i class="bi bi-info-circle-fill me-1"></i> Email is already verified.', 'info');
            } else if (detailMsg.toLowerCase().includes('expired')) {
                if (modalTitle) modalTitle.textContent = 'Verification Link Expired';
                if (modalDesc) modalDesc.textContent = 'This verification link has expired. Please log in to request a new verification email.';
                showAlert('verify-alert', '<i class="bi bi-clock-history me-1"></i> ' + detailMsg, 'warning');
            } else if (detailMsg.toLowerCase().includes('already') || detailMsg.toLowerCase().includes('used')) {
                if (modalTitle) modalTitle.textContent = 'Link Already Used';
                if (modalDesc) modalDesc.textContent = 'This verification link has already been used. Please request a new one if needed.';
                showAlert('verify-alert', '<i class="bi bi-exclamation-triangle me-1"></i> ' + detailMsg, 'warning');
            } else {
                if (modalTitle) modalTitle.textContent = 'Verification Failed';
                if (modalDesc) modalDesc.textContent = detailMsg;
                showAlert('verify-alert', '<i class="bi bi-x-circle-fill me-1"></i> ' + detailMsg, 'danger');
            }

            if (modalActions) {
                modalActions.innerHTML = `
                    <button class="btn btn-emerald w-100 py-2.5 fw-semibold rounded-3 shadow-emerald" onclick="switchToLoginAfterVerify()">
                        <i class="bi bi-box-arrow-in-right me-1"></i> Continue to Sign In
                    </button>
                `;
            }
            return;
        }

        // Success!
        if (modalIcon) {
            modalIcon.className = 'rounded-circle bg-emerald-subtle text-emerald mx-auto mb-3 mt-2 d-flex align-items-center justify-content-center shadow-sm';
            modalIcon.innerHTML = '<i class="bi bi-patch-check-fill fs-2"></i>';
        }
        if (modalTitle) modalTitle.textContent = 'Email Verified';
        if (modalDesc) modalDesc.textContent = 'Your email address has been successfully verified.';
        showAlert('verify-alert', '<i class="bi bi-patch-check-fill me-1"></i> Your email address has been successfully verified.', 'success');

        if (modalActions) {
            modalActions.innerHTML = `
                <button class="btn btn-emerald w-100 py-2.5 fw-semibold rounded-3 shadow-emerald" onclick="switchToLoginAfterVerify()">
                    <i class="bi bi-box-arrow-in-right me-1"></i> Continue to Sign In
                </button>
            `;
        }
    } catch (err) {
        if (modalIcon) {
            modalIcon.className = 'rounded-circle bg-danger-subtle text-danger mx-auto mb-3 mt-2 d-flex align-items-center justify-content-center shadow-sm';
            modalIcon.innerHTML = '<i class="bi bi-wifi-off fs-2"></i>';
        }
        showAlert('verify-alert', 'Network error while contacting verification service.', 'danger');
        if (modalActions) {
            modalActions.innerHTML = `
                <button class="btn btn-outline-secondary w-100 py-2.5 fw-semibold rounded-3" onclick="switchToLoginAfterVerify()">
                    <i class="bi bi-box-arrow-in-right me-1"></i> Continue to Sign In
                </button>
            `;
        }
    }
}

function switchToLoginAfterVerify() {
    const verifyModalEl = document.getElementById('verifyModal');
    if (verifyModalEl) bootstrap.Modal.getInstance(verifyModalEl)?.hide();

    const registerVerifyStep = document.getElementById('register-verify-step');
    if (registerVerifyStep) registerVerifyStep.classList.add('d-none');

    switchAuthTab('login');
    getModal('authModal').show();
}

function closeVerifyAndShowLogin() {
    switchToLoginAfterVerify();
}


// Backward compatibility helper
function doVerifyEmail() {
    return triggerSimulatedVerification();
}

// ─── ME (PROFILE) ────────────────────────────────────────────────────────────
async function showProfile() {
    getModal('profileModal').show();
    document.getElementById('profile-content').innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border text-emerald spinner-border-sm" role="status"></div>
            <p class="mt-2 text-muted fs-7 mb-0">Loading profile...</p>
        </div>`;

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: 'include' });
        const data = await res.json();

        if (!res.ok) {
            document.getElementById('profile-content').innerHTML =
                `<div class="alert alert-warning rounded-3 fs-7">Not authenticated. Please log in first.</div>`;
            return;
        }

        const verifiedBadge = data.is_email_verified
            ? `<span class="badge bg-emerald text-white"><i class="bi bi-patch-check-fill me-1"></i>Verified</span>`
            : `<span class="badge bg-warning text-dark"><i class="bi bi-exclamation-triangle me-1"></i>Unverified</span>`;

        document.getElementById('profile-content').innerHTML = `
            <div class="d-flex align-items-center gap-3 mt-3 mb-4">
                <div class="rounded-circle bg-emerald d-flex align-items-center justify-content-center text-white fw-bold shadow-sm"
                     style="width:56px;height:56px;font-size:1.3rem;">
                    ${data.name.charAt(0).toUpperCase()}
                </div>
                <div>
                    <h5 class="mb-0 fw-bold text-dark">${data.name}</h5>
                    <small class="text-muted">${data.email}</small>
                </div>
            </div>
            <table class="table table-sm fs-7 border-0">
                <tbody>
                    <tr><td class="text-muted fw-semibold" style="width:40%">ID</td><td><code class="fs-8">${data.id}</code></td></tr>
                    <tr><td class="text-muted fw-semibold">Email Status</td><td>${verifiedBadge}</td></tr>
                    <tr><td class="text-muted fw-semibold">Joined</td><td>${new Date(data.created_at).toLocaleDateString()}</td></tr>
                </tbody>
            </table>`;

        setNavLoggedIn(data.name);
    } catch (err) {
        document.getElementById('profile-content').innerHTML =
            `<div class="alert alert-danger rounded-3 fs-7">Network error. Is the server running?</div>`;
    }
}

// ─── LOGOUT ──────────────────────────────────────────────────────────────────
async function doLogout() {
    try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' });
    } catch (_) {}

    setNavLoggedOut();

    // Close any open modal
    ['authModal', 'profileModal', 'verifyModal', 'forgotModal'].forEach(id => {
        const el = document.getElementById(id);
        if (el) bootstrap.Modal.getInstance(el)?.hide();
    });
}

// ─── FORGOT PASSWORD ─────────────────────────────────────────────────────────
async function doForgotPassword() {
    const email = document.getElementById('forgot-email').value.trim();
    if (!email) return showAlert('forgot-alert', 'Please enter your email address.');

    const btn = document.getElementById('btn-forgot-submit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span> Sending...`;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ email })
        });
        const data = await res.json();

        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-send me-1"></i> Send Reset Link`;
        }

        showAlert('forgot-alert',
            `<i class="bi bi-envelope-check me-1"></i> ${data.message || 'If an account exists, a password reset link has been sent to your Gmail inbox. Please check your inbox.'}`,
            'info'
        );
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-send me-1"></i> Send Reset Link`;
        }
        showAlert('forgot-alert', 'Network error. Is the server running?');
    }
}

// ─── RESET PASSWORD ──────────────────────────────────────────────────────────
async function doResetPassword() {
    const token = _activeResetToken;
    const new_password = document.getElementById('reset-new-password').value;

    if (!token) {
        return showAlert('forgot-alert', 'Reset link missing or expired. Please request a new reset link.');
    }
    if (!new_password) {
        return showAlert('forgot-alert', 'Please enter your new password.');
    }
    if (new_password.length < 8) {
        return showAlert('forgot-alert', 'Password must be at least 8 characters.');
    }

    const btn = document.getElementById('btn-reset-submit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span> Updating...`;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ token, new_password })
        });
        const data = await res.json();

        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-lock-fill me-1"></i> Set New Password`;
        }

        if (!res.ok) {
            return showAlert('forgot-alert', data.detail || 'Password reset failed.');
        }

        _activeResetToken = null;
        document.getElementById('reset-new-password').value = '';
        const resetStep = document.getElementById('forgot-step-reset');
        if (resetStep) resetStep.classList.add('d-none');

        showAlert('forgot-alert',
            `<i class="bi bi-check-circle-fill me-1"></i> Password reset successfully! You can now sign in with your new password.
             <div class="mt-3">
               <button class="btn btn-emerald w-100 py-2 fw-semibold rounded-3 shadow-emerald" onclick="closeForgotAndShowLogin()">
                 <i class="bi bi-box-arrow-in-right me-1"></i> Continue to Sign In
               </button>
             </div>`,
            'success'
        );
        setNavLoggedOut();
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-lock-fill me-1"></i> Set New Password`;
        }
        showAlert('forgot-alert', 'Network error. Is the server running?');
    }
}


function closeForgotAndShowLogin() {
    const forgotModalEl = document.getElementById('forgotModal');
    if (forgotModalEl) bootstrap.Modal.getInstance(forgotModalEl)?.hide();
    switchAuthTab('login');
    getModal('authModal').show();
}

// =============================================================================
// MODULE 3 — SPACE MANAGEMENT FRONTEND LOGIC
// =============================================================================

let currentSpaces = [];

async function fetchOwnerSpaces() {
    const container = document.getElementById('spaces-list-container');
    if (!container) return;

    try {
        const res = await fetch(`${API_BASE_URL}/api/spaces`, { credentials: 'include' });
        if (!res.ok) {
            if (res.status === 401) setNavLoggedOut();
            return;
        }

        currentSpaces = await res.json();
        renderSpacesList(currentSpaces);
    } catch (err) {
        container.innerHTML = `
            <div class="alert alert-danger rounded-3 fs-7">
                <i class="bi bi-exclamation-triangle-fill me-1"></i> Failed to load Spaces. Is the server running?
            </div>`;
    }
}

function renderSpacesList(spaces) {
    const container = document.getElementById('spaces-list-container');
    if (!container) return;

    if (!spaces || spaces.length === 0) {
        container.innerHTML = `
            <div class="text-center py-5 bg-white rounded-4 shadow-sm border p-4">
                <div class="rounded-circle bg-emerald-light text-emerald mx-auto mb-3 d-flex align-items-center justify-content-center" style="width:64px;height:64px;">
                    <i class="bi bi-layers-fill fs-2"></i>
                </div>
                <h5 class="fw-bold text-dark mb-1">No Spaces Yet</h5>
                <p class="text-secondary fs-7 mb-3 max-w-400 mx-auto">Create your first branded Space to start collecting customer testimonials!</p>
                <button onclick="showSpaceModal()" class="btn btn-emerald px-4 py-2.5 fw-semibold rounded-3 shadow-sm">
                    <i class="bi bi-plus-lg me-1"></i> Create Your First Space
                </button>
            </div>`;
        return;
    }

    container.innerHTML = `
        <div class="row g-4">
            ${spaces.map(space => `
                <div class="col-md-6 col-lg-4">
                    <div class="card border-0 shadow-sm rounded-4 h-100 bg-white p-4 position-relative hover-bounce">
                        <div class="d-flex align-items-start justify-content-between mb-3">
                            <div class="d-flex align-items-center gap-3">
                                ${space.logo_url ? `
                                    <img src="${space.logo_url}" alt="Logo" class="rounded-3 border object-fit-cover" style="width:48px;height:48px;">
                                ` : `
                                    <div class="rounded-3 bg-emerald text-white fw-bold d-flex align-items-center justify-content-center shadow-sm" style="width:48px;height:48px;font-size:1.2rem;">
                                        ${space.name.charAt(0).toUpperCase()}
                                    </div>
                                `}
                                <div>
                                    <h5 class="fw-bold text-dark mb-0 fs-6">${escapeHtml(space.name)}</h5>
                                    <code class="fs-8 text-emerald fw-semibold">/collect/${escapeHtml(space.slug)}</code>
                                </div>
                            </div>
                        </div>
                        <p class="text-secondary fs-7 mb-3 text-truncate-2">
                            ${space.custom_prompt ? escapeHtml(space.custom_prompt) : '<em>No custom prompt set</em>'}
                        </p>
                        <div class="d-flex align-items-center gap-2 mb-3 fs-8">
                            <span class="badge ${space.avatar_enabled ? 'bg-emerald-subtle text-emerald' : 'bg-light text-muted'} border rounded-pill px-2.5 py-1">
                                <i class="bi bi-person-bounding-box me-1"></i> Avatar: ${space.avatar_enabled ? 'On' : 'Off'}
                            </span>
                            <span class="badge ${space.rating_enabled ? 'bg-amber-light text-amber' : 'bg-light text-muted'} border rounded-pill px-2.5 py-1">
                                <i class="bi bi-star-fill me-1"></i> Rating: ${space.rating_enabled ? 'On' : 'Off'}
                            </span>
                        </div>
                        <div class="pt-3 border-top mt-auto d-flex align-items-center justify-content-between gap-2">
                            <button onclick="previewPublicSpace('${escapeHtml(space.slug)}')" class="btn btn-outline-emerald btn-sm px-3 fw-semibold rounded-2 fs-8">
                                <i class="bi bi-box-arrow-up-right me-1"></i> View Page
                            </button>
                            <div class="d-flex gap-1">
                                <button onclick="showSpaceModal('${space.id}')" class="btn btn-outline-secondary btn-sm px-2.5 py-1 rounded-2" title="Edit Space">
                                    <i class="bi bi-pencil-square"></i>
                                </button>
                                <button onclick="confirmDeleteSpace('${space.id}', '${escapeHtml(space.name)}')" class="btn btn-outline-danger btn-sm px-2.5 py-1 rounded-2" title="Delete Space">
                                    <i class="bi bi-trash-fill"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>`;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function autoGenerateSlug(val) {
    const editId = document.getElementById('space-edit-id').value;
    if (editId) return; // Don't auto-overwrite when editing
    const slugInput = document.getElementById('space-slug');
    if (!slugInput) return;
    slugInput.value = val.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function showSpaceModal(spaceId = null) {
    clearAlert('space-modal-alert');
    const modalTitle = document.getElementById('spaceModalTitle');
    const editIdInput = document.getElementById('space-edit-id');
    const questionsContainer = document.getElementById('custom-questions-list');
    questionsContainer.innerHTML = '';

    if (spaceId) {
        const space = currentSpaces.find(s => s.id === spaceId);
        if (!space) return;

        modalTitle.innerHTML = '<i class="bi bi-pencil-square text-emerald me-2"></i>Edit Space';
        editIdInput.value = space.id;
        document.getElementById('space-name').value = space.name;
        document.getElementById('space-slug').value = space.slug;
        document.getElementById('space-prompt').value = space.custom_prompt || '';
        document.getElementById('space-logo-url').value = space.logo_url || '';
        document.getElementById('space-avatar-toggle').checked = space.avatar_enabled;
        document.getElementById('space-rating-toggle').checked = space.rating_enabled;

        updateLogoPreview(space.logo_url);

        if (space.custom_questions && space.custom_questions.length > 0) {
            space.custom_questions.forEach(q => addCustomQuestionInput(q.question));
        }
    } else {
        modalTitle.innerHTML = '<i class="bi bi-layers-fill text-emerald me-2"></i>Create New Space';
        editIdInput.value = '';
        document.getElementById('space-name').value = '';
        document.getElementById('space-slug').value = '';
        document.getElementById('space-prompt').value = '';
        document.getElementById('space-logo-url').value = '';
        document.getElementById('space-avatar-toggle').checked = true;
        document.getElementById('space-rating-toggle').checked = true;
        updateLogoPreview(null);

        // Add 1 default question
        addCustomQuestionInput("What did you like most about our service?");
    }

    getModal('spaceModal').show();
}

function updateLogoPreview(url) {
    const preview = document.getElementById('space-logo-preview');
    if (!preview) return;
    if (url) {
        preview.innerHTML = `<img src="${url}" alt="Preview" class="w-100 h-100 object-fit-cover rounded-3">`;
    } else {
        preview.innerHTML = `<i class="bi bi-image text-muted fs-4"></i>`;
    }
}

async function uploadLogoFile(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE_URL}/api/spaces/upload-logo`, {
            method: 'POST',
            credentials: 'include',
            body: formData
        });
        const data = await res.json();

        if (!res.ok) {
            return showAlert('space-modal-alert', data.detail || 'Logo upload failed.');
        }

        document.getElementById('space-logo-url').value = data.logo_url;
        updateLogoPreview(data.logo_url);
        showAlert('space-modal-alert', '<i class="bi bi-check-circle-fill me-1"></i> Logo uploaded successfully!', 'success');
    } catch (err) {
        showAlert('space-modal-alert', 'Network error uploading logo.');
    }
}

function addCustomQuestionInput(questionText = '') {
    const container = document.getElementById('custom-questions-list');
    if (!container) return;

    if (container.children.length >= 10) {
        return showAlert('space-modal-alert', 'Maximum 10 custom questions allowed.');
    }

    const div = document.createElement('div');
    div.className = 'd-flex align-items-center gap-2 custom-question-item';
    div.innerHTML = `
        <input type="text" class="form-control rounded-3 custom-question-input" placeholder="e.g. Would you recommend us?" value="${escapeHtml(questionText)}">
        <button type="button" class="btn btn-outline-danger btn-sm rounded-2 px-2.5 py-1.5" onclick="this.parentElement.remove()">
            <i class="bi bi-trash"></i>
        </button>
    `;
    container.appendChild(div);
}

async function saveSpace() {
    clearAlert('space-modal-alert');

    const editId = document.getElementById('space-edit-id').value;
    const name = document.getElementById('space-name').value.trim();
    const slug = document.getElementById('space-slug').value.trim();
    const custom_prompt = document.getElementById('space-prompt').value.trim();
    const logo_url = document.getElementById('space-logo-url').value;
    const avatar_enabled = document.getElementById('space-avatar-toggle').checked;
    const rating_enabled = document.getElementById('space-rating-toggle').checked;

    if (!name || !slug) {
        return showAlert('space-modal-alert', 'Space Name and Slug are required.');
    }

    const questionInputs = document.querySelectorAll('.custom-question-input');
    const custom_questions = [];
    questionInputs.forEach(inp => {
        const qText = inp.value.trim();
        if (qText) custom_questions.push({ question: qText });
    });

    const payload = {
        name,
        slug,
        custom_prompt: custom_prompt || null,
        logo_url: logo_url || null,
        avatar_enabled,
        rating_enabled,
        custom_questions
    };

    const isEdit = Boolean(editId);
    const url = isEdit ? `${API_BASE_URL}/api/spaces/${editId}` : `${API_BASE_URL}/api/spaces`;
    const method = isEdit ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) {
            return showAlert('space-modal-alert', data.detail || 'Failed to save space.');
        }

        getModal('spaceModal').hide();
        fetchOwnerSpaces();
    } catch (err) {
        showAlert('space-modal-alert', 'Network error. Is the server running?');
    }
}

async function confirmDeleteSpace(spaceId, spaceName) {
    if (!confirm(`Are you sure you want to delete "${spaceName}"? All related testimonials will be deleted.`)) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/spaces/${spaceId}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (!res.ok) {
            const data = await res.json();
            alert(data.detail || 'Failed to delete space.');
            return;
        }
        fetchOwnerSpaces();
    } catch (err) {
        alert('Network error deleting space.');
    }
}

async function previewPublicSpace(slug) {
    const badge = document.getElementById('public-preview-url-badge');
    const content = document.getElementById('public-space-content');
    if (badge) badge.textContent = `/collect/${slug}`;
    if (content) {
        content.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-emerald" role="status"></div>
                <p class="mt-2 text-muted fs-7 mb-0">Loading public space configuration...</p>
            </div>`;
    }
    getModal('publicSpaceModal').show();

    try {
        const res = await fetch(`${API_BASE_URL}/api/public/spaces/${slug}`);
        const data = await res.json();

        if (!res.ok) {
            content.innerHTML = `<div class="alert alert-danger rounded-3 fs-7">${data.detail || 'Space not found.'}</div>`;
            return;
        }

        content.innerHTML = `
            <div class="max-w-600 mx-auto bg-white rounded-4 shadow-sm border p-4 p-md-5">
                <div class="text-center mb-4">
                    ${data.logo_url ? `
                        <img src="${data.logo_url}" alt="${escapeHtml(data.name)}" class="rounded-3 mb-3 border" style="max-height:70px;">
                    ` : ''}
                    <h3 class="fw-extrabold text-dark mb-2">${escapeHtml(data.name)}</h3>
                    <p class="text-secondary fs-6 mb-0">
                        ${data.custom_prompt ? escapeHtml(data.custom_prompt) : 'Share your feedback with us!'}
                    </p>
                </div>

                ${data.custom_questions && data.custom_questions.length > 0 ? `
                    <div class="mb-4 pt-3 border-top">
                        <h6 class="fw-bold text-dark mb-2 fs-7 text-uppercase tracking-wider">Questions for submitters:</h6>
                        <ul class="list-group list-group-flush fs-7">
                            ${data.custom_questions.map(q => `
                                <li class="list-group-item bg-transparent px-0 text-dark">
                                    <i class="bi bi-question-circle-fill text-emerald me-2"></i>${escapeHtml(q.question)}
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                ` : ''}

                <div class="d-flex align-items-center justify-content-center gap-3 pt-3 border-top fs-8 text-muted">
                    <span><i class="bi bi-check-circle-fill text-emerald me-1"></i> Avatar: ${data.avatar_enabled ? 'Enabled' : 'Disabled'}</span>
                    <span><i class="bi bi-check-circle-fill text-emerald me-1"></i> Rating: ${data.rating_enabled ? 'Enabled' : 'Disabled'}</span>
                </div>

                <div class="mt-4 pt-3 text-center border-top">
                    <span class="badge bg-light text-muted border rounded-pill px-3 py-1.5 fs-8">
                        <i class="bi bi-info-circle me-1"></i> Public Testimonial Submission Form — Ready for Module 4
                    </span>
                </div>
            </div>`;
    } catch (err) {
        content.innerHTML = `<div class="alert alert-danger rounded-3 fs-7">Network error loading preview.</div>`;
    }
}

