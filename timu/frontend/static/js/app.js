const API_BASE_URL = "/api";

function getApiUrl(endpoint) {
    return `${API_BASE_URL}${endpoint}`;
}

window.getApiUrl = getApiUrl;

async function apiFetch(endpoint, options = {}) {
    const config = {
        method: options.method || "GET",
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        credentials: "same-origin",
    };

    if (options.body !== undefined) {
        config.body = JSON.stringify(options.body);
    }

    const response = await fetch(getApiUrl(endpoint), config);
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(payload.detail || "请求失败，请稍后重试。");
    }

    return payload;
}

function showMessage(target, message, type = "info") {
    if (!target) {
        return;
    }

    target.textContent = message || "";
    target.className = `inline-message ${message ? "visible" : ""} ${type}`;
}

function escapeHtml(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

async function initAuthPage() {
    const registerForm = document.getElementById("register-form");
    const loginForm = document.getElementById("login-form");
    const messageBox = document.getElementById("auth-message");

    try {
        const session = await apiFetch("/session/");
        if (session.authenticated) {
            window.location.href = "/dashboard/";
            return;
        }
    } catch (error) {
        showMessage(messageBox, error.message, "error");
    }

    registerForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(registerForm).entries());

        try {
            await apiFetch("/register/", { method: "POST", body: payload });
            showMessage(messageBox, "注册成功，正在跳转到工作台。", "success");
            window.setTimeout(() => {
                window.location.href = "/dashboard/";
            }, 500);
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    });

    loginForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(loginForm).entries());

        try {
            await apiFetch("/login/", { method: "POST", body: payload });
            showMessage(messageBox, "登录成功，正在跳转到工作台。", "success");
            window.setTimeout(() => {
                window.location.href = "/dashboard/";
            }, 500);
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    });
}

function buildApplicantForm(requestItem) {
    const form = document.getElementById("purchase-form");
    if (!form) {
        return;
    }

    form.elements.request_id.value = requestItem?.id || "";
    form.elements.item_name.value = requestItem?.item_name || "";
    form.elements.quantity.value = requestItem?.quantity || "";
    form.elements.amount.value = requestItem?.amount || "";
    form.elements.purpose.value = requestItem?.purpose || "";
}

function timelineMarkup(item) {
    if (!item.timeline?.length) {
        return '<p class="muted">暂无流转记录</p>';
    }

    return item.timeline
        .map(
            (record) => `
                <div class="timeline-item">
                    <strong>${escapeHtml(record.action_label)}</strong>
                    <span>${escapeHtml(record.actor)} · ${escapeHtml(record.actor_role)}</span>
                    <span>${escapeHtml(record.created_at)}</span>
                    <p>${escapeHtml(record.comment || "无备注")}</p>
                </div>
            `
        )
        .join("");
}

function actionsMarkup(item, currentUser) {
    if (!currentUser) {
        return "";
    }

    if (currentUser.role === "applicant") {
        const disabled = item.is_editable ? "" : "disabled";
        return `
            <div class="actions">
                <button class="button button-secondary js-edit" type="button" data-id="${item.id}" ${disabled}>编辑</button>
                <button class="button js-submit" type="button" data-id="${item.id}" ${disabled}>提交申请</button>
            </div>
        `;
    }

    if (currentUser.role !== item.current_reviewer_role) {
        return "";
    }

    return `
        <div class="review-panel" data-request-id="${item.id}">
            <div class="review-actions">
                <button class="button js-approve" type="button" data-id="${item.id}">通过</button>
                <button class="button button-secondary js-reject" type="button" data-id="${item.id}">打回申请</button>
            </div>
            <label class="review-reason-label">
                打回理由
                <textarea
                    class="reason-input"
                    data-id="${item.id}"
                    rows="3"
                    placeholder="请输入打回原因，提交时将一并发送"
                ></textarea>
            </label>
        </div>
    `;
}

function requestCardMarkup(item, currentUser) {
    const rejectionBlock = item.rejection_reason
        ? `<div class="notice warning">打回原因：${escapeHtml(item.rejection_reason)}</div>`
        : "";

    return `
        <article class="request-card">
            <div class="request-head">
                <div>
                    <h3>${escapeHtml(item.item_name)}</h3>
                    <p class="section-meta">${escapeHtml(item.applicant)} · 数量 ${item.quantity} · 金额 ¥${escapeHtml(item.amount)}</p>
                </div>
                <div class="badge-group">
                    <span class="badge">${escapeHtml(item.status_label)}</span>
                    <span class="badge badge-light">${escapeHtml(item.current_reviewer_label)}</span>
                </div>
            </div>
            <p>${escapeHtml(item.purpose)}</p>
            ${rejectionBlock}
            <div class="meta-grid">
                <span>提交时间：${escapeHtml(item.submitted_at || "未提交")}</span>
                <span>完成时间：${escapeHtml(item.approved_at || "未完成")}</span>
            </div>
            ${actionsMarkup(item, currentUser)}
            <div class="timeline">
                ${timelineMarkup(item)}
            </div>
        </article>
    `;
}

async function initDashboardPage() {
    const sessionSummary = document.getElementById("session-summary");
    const tableTitle = document.getElementById("table-title");
    const tableHint = document.getElementById("table-hint");
    const requestList = document.getElementById("request-list");
    const messageBox = document.getElementById("dashboard-message");
    const logoutBtn = document.getElementById("logout-btn");
    const applicantPanel = document.getElementById("applicant-panel");
    const purchaseForm = document.getElementById("purchase-form");
    const resetFormBtn = document.getElementById("reset-form-btn");

    let currentUser = null;
    let currentItems = [];

    async function loadSession() {
        const session = await apiFetch("/session/");
        if (!session.authenticated) {
            window.location.href = "/register/";
            return;
        }

        currentUser = session.user;
        sessionSummary.textContent = `${currentUser.display_name}，当前角色：${currentUser.role_label}。`;
        applicantPanel?.classList.toggle("hidden", currentUser.role !== "applicant");

        if (currentUser.role === "applicant") {
            tableTitle.textContent = "我的申请记录";
            tableHint.textContent = "可编辑待提交与已打回申请，并重新发起审批。";
            return;
        }

        if (currentUser.role === "finance") {
            tableTitle.textContent = "财务审批列表";
            tableHint.textContent = "仅展示当前待你审批或你已参与处理的申请。";
            return;
        }

        tableTitle.textContent = "导师总览";
        tableHint.textContent = "可查看全部申请，并处理高金额流程的最终审批。";
    }

    async function loadRequests() {
        const payload = await apiFetch("/purchases/");
        currentItems = payload.results || [];
        requestList.innerHTML = currentItems.length
            ? currentItems.map((item) => requestCardMarkup(item, currentUser)).join("")
            : '<div class="empty-state">当前没有可展示的申请。</div>';
    }

    async function refresh() {
        try {
            await loadSession();
            await loadRequests();
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    }

    logoutBtn?.addEventListener("click", async () => {
        try {
            await apiFetch("/logout/", { method: "POST" });
            window.location.href = "/register/";
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    });

    purchaseForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(purchaseForm).entries());
        const requestId = payload.request_id;
        delete payload.request_id;

        try {
            if (requestId) {
                await apiFetch(`/purchases/${requestId}/`, { method: "PATCH", body: payload });
                showMessage(messageBox, "申请已更新。", "success");
            } else {
                await apiFetch("/purchases/", { method: "POST", body: payload });
                showMessage(messageBox, "申请草稿已创建。", "success");
            }

            buildApplicantForm(null);
            await refresh();
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    });

    resetFormBtn?.addEventListener("click", () => {
        buildApplicantForm(null);
        showMessage(messageBox, "", "info");
    });

    requestList?.addEventListener("click", async (event) => {
        const target = event.target.closest("button[data-id]");
        if (!target) {
            return;
        }

        const requestId = target.dataset.id;

        try {
            if (target.classList.contains("js-edit")) {
                const matched = currentItems.find((item) => String(item.id) === String(requestId));
                buildApplicantForm(matched);
                window.scrollTo({ top: 0, behavior: "smooth" });
                return;
            }

            if (target.classList.contains("js-submit")) {
                await apiFetch(`/purchases/${requestId}/submit/`, { method: "POST" });
                showMessage(messageBox, "申请已提交。", "success");
                await refresh();
                return;
            }

            if (target.classList.contains("js-approve")) {
                await apiFetch(`/purchases/${requestId}/approve/`, { method: "POST" });
                showMessage(messageBox, "审批已通过。", "success");
                await refresh();
                return;
            }

            if (target.classList.contains("js-reject")) {
                const reviewPanel = target.closest(".review-panel");
                const input = reviewPanel?.querySelector(`.reason-input[data-id="${requestId}"]`);
                const reason = (input?.value || "").trim();

                if (!reason) {
                    showMessage(messageBox, "请先填写打回理由，再提交打回。", "error");
                    input?.focus();
                    return;
                }

                await apiFetch(`/purchases/${requestId}/reject/`, {
                    method: "POST",
                    body: { reason },
                });
                showMessage(messageBox, "申请已打回。", "success");
                await refresh();
            }
        } catch (error) {
            showMessage(messageBox, error.message, "error");
        }
    });

    await refresh();
}

document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;

    if (page === "auth") {
        initAuthPage();
    }

    if (page === "dashboard") {
        initDashboardPage();
    }
});
