// Quick Compare — Frontend JavaScript

// Use absolute URL for local separate development, relative for combined deployment
const API_BASE = window.location.port === '5500' || window.location.port === '3000' 
    ? 'http://127.0.0.1:8000' 
    : '';

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const pincodeInput = document.getElementById('pincodeInput');
const loadingState = document.getElementById('loadingState');
const resultsSection = document.getElementById('resultsSection');
const errorState = document.getElementById('errorState');
const errorMessage = document.getElementById('errorMessage');
const retryBtn = document.getElementById('retryBtn');
const summaryCards = document.getElementById('summaryCards');
const resultsGrid = document.getElementById('resultsGrid');
const platformStatus = document.getElementById('platformStatus');
const comparisonsList = document.getElementById('comparisonsList');
const comparisonsSection = document.getElementById('comparisonsSection');
const errorsContainer = document.getElementById('errorsContainer');

// State
let currentResults = null;
let activeFilter = 'all';

// Platform config
const PLATFORM = {
    Blinkit: { color: '#f7ca00', text: '#000', icon: '🟡' },
    DMart: { color: '#00a650', text: '#fff', icon: '🟢' },
    JioMart: { color: '#0a2885', text: '#fff', icon: '🔵' },
    Instamart: { color: '#fc8019', text: '#fff', icon: '🟠' },
};

// ─────────────────────────────────────────────
// Initialize
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.protocol === 'file:') {
        alert('⚠️ Please open http://127.0.0.1:8000 instead of this file directly.');
        showError('Please open http://127.0.0.1:8000 to use this app.');
        return;
    }

    searchBtn.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    retryBtn.addEventListener('click', handleSearch);

    // Platform filter tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            activeFilter = e.target.dataset.platform;
            renderAllResults();
        });
    });
});

// ─────────────────────────────────────────────
// Search
// ─────────────────────────────────────────────

async function handleSearch() {
    const query = searchInput.value.trim();
    if (!query) { searchInput.focus(); return; }

    const pincode = pincodeInput.value.trim() || '380015';
    showLoading();

    try {
        const isHeadful = document.getElementById('headfulCheckbox').checked;

        const response = await fetch(`${API_BASE}/api/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query,
                pincode,
                lat: 23.0225,
                lng: 72.5714,
                max_results: 40,
                headful: isHeadful,
            }),
        });

        if (!response.ok) throw new Error(`Search failed: ${response.statusText}`);

        currentResults = await response.json();
        console.log('Results:', currentResults);
        showResults();

    } catch (error) {
        console.error('Search error:', error);
        showError(error.message);
    }
}

// ─────────────────────────────────────────────
// UI States
// ─────────────────────────────────────────────

function showLoading() {
    loadingState.classList.remove('hidden');
    resultsSection.classList.add('hidden');
    errorState.classList.add('hidden');
}

function showResults() {
    loadingState.classList.add('hidden');
    errorState.classList.add('hidden');
    resultsSection.classList.remove('hidden');

    renderSummary();
    renderErrors();
    renderComparisons();
    renderAllResults();
}

function showError(message) {
    loadingState.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorState.classList.remove('hidden');
    errorMessage.textContent = message || 'Something went wrong. Please try again.';
}

// ─────────────────────────────────────────────
// Render: Summary bar
// ─────────────────────────────────────────────

function renderSummary() {
    if (!currentResults) return;
    const { all_results, by_platform, comparisons, errors } = currentResults;

    const platformCounts = Object.entries(by_platform || {})
        .map(([name, items]) => `${name}: ${items.length}`)
        .join('  |  ');

    summaryCards.innerHTML = `
        <div class="summary-card accent">
            <div class="value">${all_results?.length || 0}</div>
            <div class="label">Total Products</div>
        </div>
        <div class="summary-card">
            <div class="value">${Object.keys(by_platform || {}).filter(k => (by_platform[k]?.length || 0) > 0).length}</div>
            <div class="label">Platforms</div>
        </div>
        <div class="summary-card">
            <div class="value">${comparisons?.length || 0}</div>
            <div class="label">Cross-Platform Matches</div>
        </div>
        <div class="summary-card ${errors?.length ? 'error' : ''}">
            <div class="value">${errors?.length || 0}</div>
            <div class="label">Failures</div>
        </div>
    `;
}

// ─────────────────────────────────────────────
// Render: Errors
// ─────────────────────────────────────────────

function renderErrors() {
    if (!currentResults?.errors || currentResults.errors.length === 0) {
        errorsContainer.classList.add('hidden');
        return;
    }
    errorsContainer.classList.remove('hidden');
    errorsContainer.innerHTML = currentResults.errors.map(e =>
        `<div class="error-badge">⚠️ ${esc(e.platform)} failed: ${esc(e.error).substring(0, 100)}</div>`
    ).join('');
}

// ─────────────────────────────────────────────
// Render: Comparison Groups
// ─────────────────────────────────────────────

function renderComparisons() {
    const groups = currentResults?.comparisons;
    if (!groups || groups.length === 0) {
        comparisonsSection.classList.add('hidden');
        return;
    }

    comparisonsSection.classList.remove('hidden');

    comparisonsList.innerHTML = groups.map((group, idx) => {
        // Find the best deal in this group
        const priced = group.filter(p => p.price);
        const bestPrice = priced.length ? Math.min(...priced.map(p => p.price)) : null;

        const cards = group.map(item => {
            const isBest = item.price === bestPrice && priced.length > 1;
            return renderComparisonCard(item, isBest);
        }).join('');

        // Show savings banner if applicable
        let savingsBanner = '';
        if (priced.length > 1) {
            const maxP = Math.max(...priced.map(p => p.price));
            const minP = Math.min(...priced.map(p => p.price));
            if (maxP > minP) {
                const save = (maxP - minP).toFixed(0);
                savingsBanner = `<div class="savings-banner">💰 Save up to ₹${save} by choosing the best platform!</div>`;
            }
        }

        return `
            <div class="comparison-group">
                <div class="comparison-header">
                    <span class="comparison-title">${esc(group[0].name)}</span>
                    <span class="comparison-count">${group.length} platforms</span>
                </div>
                ${savingsBanner}
                <div class="comparison-cards">${cards}</div>
            </div>
        `;
    }).join('');
}

function renderComparisonCard(item, isBest) {
    const pConf = PLATFORM[item.platform] || { color: '#666', text: '#fff' };
    return `
        <div class="comp-card ${isBest ? 'best' : ''}">
            ${isBest ? '<div class="best-badge">🏆 Best Price</div>' : ''}
            <div class="comp-platform" style="background:${pConf.color};color:${pConf.text}">${esc(item.platform)}</div>
            ${item.image_url ? imgTag(item.image_url, item.name, 'comp-img') : ''}
            <div class="comp-name">${esc(item.name)}</div>
            <div class="comp-price-row">
                <span class="comp-price">₹${item.price?.toFixed(2) || 'N/A'}</span>
                ${item.original_price && item.original_price > item.price
            ? `<span class="comp-mrp">₹${item.original_price.toFixed(2)}</span>`
            : ''}
            </div>
            ${item.discount ? `<span class="comp-discount">${esc(item.discount)}</span>` : ''}
            ${item.quantity ? `<div class="comp-qty">${esc(item.quantity)}</div>` : ''}
            ${item.unit_price ? `<div class="comp-unit">₹${item.unit_price.toFixed(2)}/g</div>` : ''}
            ${item.link ? `<a class="comp-link" href="${item.link}" target="_blank" rel="noopener">View on ${esc(item.platform)} →</a>` : ''}
        </div>
    `;
}

// ─────────────────────────────────────────────
// Render: All Results Grid
// ─────────────────────────────────────────────

function renderAllResults() {
    if (!currentResults?.all_results || currentResults.all_results.length === 0) {
        resultsGrid.innerHTML = '<p class="empty-msg">No results found. Try a different search term.</p>';
        return;
    }

    let results = currentResults.all_results;
    if (activeFilter !== 'all') {
        results = results.filter(r => r.platform === activeFilter);
    }

    if (results.length === 0) {
        resultsGrid.innerHTML = `<p class="empty-msg">No results found for ${activeFilter}.</p>`;
        return;
    }

    resultsGrid.innerHTML = results.map(item => {
        const pConf = PLATFORM[item.platform] || { color: '#666', text: '#fff' };
        const isBest = item.is_best_deal;

        return `
            <div class="result-card ${isBest ? 'best-deal' : ''} ${!item.in_stock ? 'oos' : ''}">
                ${isBest ? '<div class="card-best-badge">🏆 Best Deal</div>' : ''}
                ${!item.in_stock ? '<div class="oos-badge">Out of Stock</div>' : ''}

                <div class="card-top">
                    <span class="platform-badge" style="background:${pConf.color};color:${pConf.text}">${esc(item.platform)}</span>
                    ${item.discount ? `<span class="discount-badge">${esc(item.discount)}</span>` : ''}
                </div>

                ${item.image_url
                ? `<div class="card-image">${imgTag(item.image_url, item.name)}</div>`
                : ''
            }

                <div class="card-body">
                    <div class="card-name">${esc(item.name)}</div>

                    <div class="card-price-row">
                        <span class="card-price">₹${item.price?.toFixed(2) || 'N/A'}</span>
                        ${item.original_price && item.original_price > item.price
                ? `<span class="card-mrp">₹${item.original_price.toFixed(2)}</span>`
                : ''
            }
                    </div>

                    <div class="card-meta">
                        ${item.quantity ? `<span>📦 ${esc(item.quantity)}</span>` : ''}
                        ${item.unit_price ? `<span>⚖️ ₹${item.unit_price.toFixed(2)}/g</span>` : ''}
                    </div>

                    ${item.savings ? `<div class="card-savings">${esc(item.savings)}</div>` : ''}
                </div>

                ${item.link ? `<a class="card-link" href="${item.link}" target="_blank" rel="noopener">View Product →</a>` : ''}
            </div>
        `;
    }).join('');
}

// ─────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────

function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Route image through our backend proxy to bypass CDN Referer blocking.
 * Falls back to direct URL if proxy is unavailable.
 */
function imgSrc(url) {
    if (!url) return '';
    return `${API_BASE}/api/image-proxy?url=${encodeURIComponent(url)}`;
}

/**
 * Build an <img> tag with proxy URL, referrerpolicy, and fallback.
 */
function imgTag(url, alt, cssClass, extraStyle) {
    if (!url) return '';
    const cls = cssClass ? ` class="${cssClass}"` : '';
    const style = extraStyle ? ` style="${extraStyle}"` : '';
    return `<img${cls}${style} src="${imgSrc(url)}" alt="${esc(alt || '')}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src='${esc(url)}'; this.style.opacity='0.5'">`;
}
