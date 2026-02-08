/**
 * TraceBoard — Alpine.js Application
 *
 * Connects to the server via WebSocket for near-real-time updates.
 * Falls back to HTTP polling (3 s interval) when WebSocket is unavailable.
 */

function app() {
    return {
        // ── State ──────────────────────────────────────────────────
        currentView: 'metrics',   // 'metrics' | 'traces' | 'detail'
        autoRefresh: true,
        refreshInterval: null,

        // WebSocket
        ws: null,
        wsConnected: false,
        _wsReconnectTimer: null,

        // Traces list
        traces: [],
        totalTraces: 0,
        currentPage: 1,
        pageSize: 50,
        filterStatus: '',

        // Metrics
        metrics: {
            total_traces: 0,
            total_spans: 0,
            total_tokens: 0,
            total_cost: 0.0,
            avg_duration_ms: 0.0,
            error_count: 0,
            traces_by_status: {},
            cost_by_model: {},
        },

        // Detail view
        selectedTrace: null,
        selectedSpan: null,

        // Depth cache for span tree indentation
        _depthCache: {},

        // ── Init ───────────────────────────────────────────────────

        async init() {
            await this.loadMetrics();
            await this.loadTraces();
            this.connectWebSocket();
        },

        // ── WebSocket ─────────────────────────────────────────────

        connectWebSocket() {
            if (this._wsReconnectTimer) {
                clearTimeout(this._wsReconnectTimer);
                this._wsReconnectTimer = null;
            }

            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/api/ws/live`;

                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    this.wsConnected = true;
                    // WebSocket takes over — stop REST polling
                    if (this.refreshInterval) {
                        clearInterval(this.refreshInterval);
                        this.refreshInterval = null;
                    }
                };

                this.ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        this.handleWsMessage(msg);
                    } catch (e) {
                        console.error('Failed to parse WebSocket message:', e);
                    }
                };

                this.ws.onclose = () => {
                    this.wsConnected = false;
                    this.startPolling();
                    // Attempt reconnect after 3 seconds
                    this._wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
                };

                this.ws.onerror = () => {
                    // onclose fires after onerror — reconnect handled there
                };
            } catch (e) {
                console.warn('WebSocket unavailable, using polling fallback.');
                this.startPolling();
            }
        },

        handleWsMessage(msg) {
            if (msg.type === 'pong') return;

            if (msg.type === 'update') {
                // Always update metrics from the push
                if (msg.metrics) {
                    this.metrics = msg.metrics;
                }

                // Refresh the active view when auto-refresh is on
                if (this.autoRefresh) {
                    if (this.currentView === 'traces') {
                        this.loadTraces();
                    } else if (this.currentView === 'detail' && this.selectedTrace) {
                        this.viewTrace(this.selectedTrace.trace.trace_id);
                    }
                }
            }
        },

        startPolling() {
            if (this.refreshInterval) return;
            this.refreshInterval = setInterval(() => {
                if (this.autoRefresh) {
                    if (this.currentView === 'metrics') {
                        this.loadMetrics();
                    } else if (this.currentView === 'traces') {
                        this.loadTraces();
                    } else if (this.currentView === 'detail' && this.selectedTrace) {
                        this.viewTrace(this.selectedTrace.trace.trace_id);
                    }
                }
            }, 3000);
        },

        // ── API Calls ──────────────────────────────────────────────

        async loadMetrics() {
            try {
                const resp = await fetch('/api/metrics');
                if (resp.ok) {
                    this.metrics = await resp.json();
                }
            } catch (e) {
                console.error('Failed to load metrics:', e);
            }
        },

        async loadTraces() {
            try {
                let url = `/api/traces?page=${this.currentPage}&page_size=${this.pageSize}`;
                if (this.filterStatus) url += `&status=${this.filterStatus}`;

                const resp = await fetch(url);
                if (resp.ok) {
                    const data = await resp.json();
                    this.traces = data.traces;
                    this.totalTraces = data.total;
                }
            } catch (e) {
                console.error('Failed to load traces:', e);
            }
        },

        async viewTrace(traceId) {
            try {
                const resp = await fetch(`/api/traces/${traceId}`);
                if (resp.ok) {
                    this.selectedTrace = await resp.json();
                    this.selectedSpan = null;
                    this._depthCache = {};

                    // Pre-compute depth for each span
                    if (this.selectedTrace.spans) {
                        const parentMap = {};
                        this.selectedTrace.spans.forEach(s => {
                            parentMap[s.span_id] = s.parent_id;
                        });
                        this.selectedTrace.spans.forEach(s => {
                            this._depthCache[s.span_id] = this._computeDepth(s.span_id, parentMap);
                        });
                    }

                    this.currentView = 'detail';
                }
            } catch (e) {
                console.error('Failed to load trace:', e);
            }
        },

        // ── Helpers ────────────────────────────────────────────────

        _computeDepth(spanId, parentMap, seen = new Set()) {
            if (seen.has(spanId)) return 0;
            seen.add(spanId);
            const parentId = parentMap[spanId];
            if (!parentId || !parentMap.hasOwnProperty(parentId)) return 0;
            return 1 + this._computeDepth(parentId, parentMap, seen);
        },

        getSpanDepth(span) {
            return this._depthCache[span.span_id] || 0;
        },

        getTimelineBarStyle(span) {
            if (!this.selectedTrace || !this.selectedTrace.spans.length) return '';

            const traceStart = this.selectedTrace.trace.started_at;
            const traceEnd = this.selectedTrace.trace.ended_at || Date.now() / 1000;
            const traceDuration = traceEnd - traceStart;

            if (traceDuration <= 0) return 'left: 0%; width: 100%;';

            const spanStart = span.started_at - traceStart;
            const spanEnd = (span.ended_at || traceEnd) - traceStart;
            const spanDuration = spanEnd - spanStart;

            const left = Math.max(0, (spanStart / traceDuration) * 100);
            const width = Math.max(1, (spanDuration / traceDuration) * 100);

            return `left: ${left.toFixed(2)}%; width: ${width.toFixed(2)}%;`;
        },

        spanColor(type) {
            const colors = {
                agent: 'bg-blue-500',
                generation: 'bg-purple-500',
                function: 'bg-amber-500',
                guardrail: 'bg-cyan-500',
                handoff: 'bg-pink-500',
                custom: 'bg-gray-500',
                transcription: 'bg-teal-500',
                speech: 'bg-orange-500',
                speech_group: 'bg-orange-400',
            };
            return colors[type] || 'bg-gray-500';
        },

        spanBarColor(type) {
            const colors = {
                agent: 'bg-blue-500/60',
                generation: 'bg-purple-500/60',
                function: 'bg-amber-500/60',
                guardrail: 'bg-cyan-500/60',
                handoff: 'bg-pink-500/60',
                custom: 'bg-gray-500/60',
                transcription: 'bg-teal-500/60',
                speech: 'bg-orange-500/60',
                speech_group: 'bg-orange-400/60',
            };
            return colors[type] || 'bg-gray-500/60';
        },

        formatNumber(n) {
            if (n === null || n === undefined) return '0';
            if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
            if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
            return n.toString();
        },

        formatDuration(ms) {
            if (ms === null || ms === undefined) return '-';
            if (ms < 1) return '<1ms';
            if (ms < 1000) return Math.round(ms) + 'ms';
            if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
            return (ms / 60000).toFixed(1) + 'm';
        },

        formatTime(timestamp) {
            if (!timestamp) return '-';
            const d = new Date(timestamp * 1000);
            return d.toLocaleTimeString() + ' ' + d.toLocaleDateString();
        },
    };
}
