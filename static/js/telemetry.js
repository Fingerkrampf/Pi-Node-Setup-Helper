/**
 * Pi Node Setup Helper - Telemetry Client v11.1
 * Handles anonymous error tracking and usage statistics.
 * Mandatory for tool usage.
 */

window.Telemetry = (function() {
    'use strict';

    const CONFIG = {
        url: window.VITE_TELEMETRY_URL || 'http://85.215.174.90:8080',
        version: window.APP_VERSION || '11.1',
        consentKey: 'pi_node_telemetry_consent',
        queueKey: 'pi_node_telemetry_queue'
    };

    let hasConsent = localStorage.getItem(CONFIG.consentKey) === 'true';
    const errorCache = new Map(); // message -> timestamp

    // Initialize: Hook into global errors
    function init() {
        window.onerror = function(message, source, lineno, colno, error) {
            logError({
                message,
                source,
                lineno,
                colno,
                stack: error ? error.stack : null,
                type: 'runtime_error'
            });
        };

        window.onunhandledrejection = function(event) {
            logError({
                message: event.reason ? event.reason.message || event.reason.toString() : 'Unhandled Promise Rejection',
                stack: event.reason ? event.reason.stack : null,
                type: 'unhandled_promise'
            });
        };

        if (hasConsent) {
            flushQueue();
        }
    }

    function setConsent(value) {
        hasConsent = !!value;
        localStorage.setItem(CONFIG.consentKey, hasConsent.toString());
        if (hasConsent) {
            logEvent('consent_granted');
            flushQueue();
        }
    }

    function getConsent() {
        return localStorage.getItem(CONFIG.consentKey);
    }

    async function logEvent(name, data = {}) {
        const payload = {
            event: name,
            version: CONFIG.version,
            os: navigator.platform,
            nodeId: window.NODE_ID || 'unknown',
            timestamp: new Date().toISOString(),
            metadata: {
                ...data,
                screen: `${window.screen.width}x${window.screen.height}`,
                lang: navigator.language,
                cores: navigator.hardwareConcurrency || 'unknown',
                connection: navigator.connection ? navigator.connection.effectiveType : 'unknown'
            }
        };

        if (!hasConsent) {
            enqueue({ endpoint: '/api/telemetry/event', data: payload });
            return;
        }

        try {
            await fetch(`${CONFIG.url}/api/telemetry/event`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.error('Telemetry event failed', e);
        }
    }

    async function logError(errorData) {
        const now = Date.now();
        const msg = errorData.message || 'unknown';
        const lastSent = errorCache.get(msg);
        if (lastSent && (now - lastSent < 60000)) return;
        errorCache.set(msg, now);

        const payload = {
            message: errorData.message || 'unknown error',
            source: errorData.source || 'js_frontend',
            type: errorData.type || 'error',
            nodeId: window.NODE_ID || 'unknown',
            os: navigator.platform,
            arch: 'unknown',
            lineno: errorData.lineno,
            colno: errorData.colno,
            stack: errorData.stack,
            version: CONFIG.version,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            metadata: {
                screen: `${window.screen.width}x${window.screen.height}`,
                lang: navigator.language,
                cores: navigator.hardwareConcurrency || 'unknown',
                connection: navigator.connection ? navigator.connection.effectiveType : 'unknown'
            }
        };

        if (!hasConsent) {
            enqueue({ endpoint: '/api/telemetry/error', data: payload });
            return;
        }

        try {
            await fetch(`${CONFIG.url}/api/telemetry/error`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.error('Telemetry error failed', e);
        }
    }

    function enqueue(item) {
        try {
            const queue = JSON.parse(localStorage.getItem(CONFIG.queueKey) || '[]');
            queue.push(item);
            localStorage.setItem(CONFIG.queueKey, JSON.stringify(queue.slice(-50)));
        } catch (e) {}
    }

    async function flushQueue() {
        if (!hasConsent) return;
        try {
            const queue = JSON.parse(localStorage.getItem(CONFIG.queueKey) || '[]');
            if (queue.length === 0) return;

            localStorage.removeItem(CONFIG.queueKey);
            for (const item of queue) {
                try {
                    await fetch(CONFIG.url + item.endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(item.data)
                    });
                } catch (e) {}
            }
        } catch (e) {}
    }

    return {
        init: init,
        logEvent: logEvent,
        logError: logError,
        setConsent: setConsent,
        getConsent: getConsent
    };
})();
