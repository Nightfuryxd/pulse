/**
 * PULSE Node.js SDK
 *
 * Drop-in observability for any Node.js application.
 * Ships errors, slow queries, traces, and custom events to PULSE.
 *
 * Quick start:
 *   const pulse = require('@pulse/sdk');
 *   pulse.init({ url: 'http://pulse:8000', service: 'my-api' });
 *
 * Express middleware:
 *   app.use(pulse.expressMiddleware());
 *
 * Manual:
 *   pulse.captureException(err);
 *   pulse.captureEvent('user_signup', { userId: 123 });
 *   const span = pulse.startSpan('db.query'); ... span.finish();
 */

'use strict';

const http      = require('http');
const https     = require('https');
const os        = require('os');
const { v4: uuidv4 } = (() => { try { return require('uuid'); } catch { return { v4: () => Math.random().toString(36).slice(2) }; } })();

// ── State ─────────────────────────────────────────────────────────────────────
let _apiUrl   = '';
let _service  = 'app';
let _nodeId   = process.env.NODE_ID || os.hostname();
let _enabled  = false;
let _logQueue = [];
let _spanQueue = [];
let _flushTimer = null;
let _flushInterval = 5000; // ms

// ── Init ──────────────────────────────────────────────────────────────────────
function init({ url, service, nodeId, flushInterval = 5000, captureUnhandled = true, autoInstrument = true } = {}) {
  _apiUrl         = url.replace(/\/$/, '');
  _service        = service || 'app';
  _nodeId         = nodeId  || _nodeId;
  _flushInterval  = flushInterval;
  _enabled        = true;

  if (captureUnhandled) _installExceptionHandlers();
  if (autoInstrument)   _autoInstrument();

  _flushTimer = setInterval(_flush, _flushInterval);
  if (_flushTimer.unref) _flushTimer.unref(); // don't keep process alive

  console.log(`[PULSE SDK] Initialized — service=${_service} node=${_nodeId} api=${_apiUrl}`);
}

// ── Core capture ──────────────────────────────────────────────────────────────
function captureException(err, { extra = {}, traceId } = {}) {
  if (!_enabled || !err) return;
  const stack = err.stack || String(err);
  _queueLog({
    level:    'error',
    message:  `${err.name || 'Error'}: ${err.message || err}`,
    source:   'exception',
    trace_id: traceId,
    extra:    { stack: stack.slice(0, 3000), ...extra },
  });
  _sendEvent({
    node_id:  _nodeId,
    type:     'app_exception',
    severity: 'high',
    source:   `sdk:${_service}`,
    message:  `[${_service}] ${err.name || 'Error'}: ${String(err.message || err).slice(0, 300)}`,
    data:     { service: _service, exception: err.name || 'Error', stack: stack.slice(0, 2000), ...extra },
  });
}

function captureEvent(name, data = {}, severity = 'info') {
  if (!_enabled) return;
  _sendEvent({
    node_id:  _nodeId,
    type:     name,
    severity,
    source:   `sdk:${_service}`,
    message:  name,
    data,
  });
}

function log(entry) {
  if (!_enabled) return;
  _queueLog({
    node_id: _nodeId,
    service: _service,
    ts:      new Date().toISOString(),
    level:   'info',
    ...entry,
  });
}

const info  = (msg, extra) => log({ level: 'info',  message: msg, extra });
const warn  = (msg, extra) => log({ level: 'warn',  message: msg, extra });
const error = (msg, extra) => log({ level: 'error', message: msg, extra });
const debug = (msg, extra) => log({ level: 'debug', message: msg, extra });

// ── Tracing ───────────────────────────────────────────────────────────────────
class Span {
  constructor(operation, { service, parentId, traceId } = {}) {
    this.operation  = operation;
    this.service    = service || _service;
    this.traceId    = traceId || uuidv4();
    this.spanId     = uuidv4().slice(0, 8);
    this.parentId   = parentId || null;
    this.startedAt  = Date.now();
    this.tags       = {};
    this._error     = null;
  }

  setTag(key, value)   { this.tags[key] = String(value); return this; }
  setError(err)        { this._error = `${err.name || 'Error'}: ${err.message}`; return this; }

  finish(status = 'ok') {
    const durationMs = Date.now() - this.startedAt;
    try {
      _spanQueue.push({
        node_id:     _nodeId,
        service:     this.service,
        trace_id:    this.traceId,
        span_id:     this.spanId,
        parent_id:   this.parentId,
        operation:   this.operation,
        ts:          new Date().toISOString(),
        duration_ms: durationMs,
        status:      this._error ? 'error' : status,
        tags:        this.tags,
        error:       this._error,
      });
    } catch (_) {}
  }
}

function startSpan(operation, opts) {
  return new Span(operation, opts);
}

async function withSpan(operation, fn, opts) {
  const span = new Span(operation, opts);
  try {
    const result = await fn(span);
    span.finish('ok');
    return result;
  } catch (err) {
    span.setError(err);
    span.finish('error');
    throw err;
  }
}

// ── Express middleware ────────────────────────────────────────────────────────
function expressMiddleware({ slowThresholdMs = 2000 } = {}) {
  return function pulseMiddleware(req, res, next) {
    const start   = Date.now();
    const traceId = req.headers['x-trace-id'] || uuidv4().slice(0, 8);
    req.pulseTraceId = traceId;

    res.on('finish', () => {
      const durationMs = Date.now() - start;
      const status     = res.statusCode;
      if (status >= 500 || durationMs >= slowThresholdMs) {
        const span = startSpan(`http.${req.method.toLowerCase()}`, { traceId });
        span.setTag('http.path',     req.path);
        span.setTag('http.method',   req.method);
        span.setTag('http.status',   String(status));
        span.setTag('http.duration', `${durationMs}ms`);
        if (status >= 500) span.setError(new Error(`HTTP ${status}`));
        span.finish(status >= 500 ? 'error' : 'ok');
      }
    });

    next();
  };
}

// ── Auto-instrumentation ──────────────────────────────────────────────────────
function _autoInstrument() {
  _patchPg();
  _patchMongoose();
  _patchAxios();
  _patchFetch();
}

function _patchPg() {
  try {
    const pg = require('pg');
    const orig = pg.Client.prototype.query;
    pg.Client.prototype.query = function(config, values, cb) {
      const start = Date.now();
      const result = orig.apply(this, arguments);
      const finish = () => {
        const ms = Date.now() - start;
        const threshold = parseInt(process.env.PULSE_SLOW_QUERY_MS || '500');
        if (ms >= threshold) {
          const span = startSpan('db.query.slow');
          span.setTag('db.type', 'postgres');
          span.setTag('db.statement', String(config?.text || config || '').slice(0, 200));
          span.setTag('db.duration_ms', String(ms));
          span.finish('ok');
        }
      };
      if (result && result.then) result.then(finish, finish);
      else finish();
      return result;
    };
  } catch (_) {}
}

function _patchMongoose() {
  try {
    const mongoose = require('mongoose');
    mongoose.plugin((schema) => {
      schema.pre(/^(find|findOne|save|update|delete)/, function() {
        this._pulseStart = Date.now();
      });
      schema.post(/^(find|findOne|save|update|delete)/, function() {
        const ms = Date.now() - (this._pulseStart || Date.now());
        const threshold = parseInt(process.env.PULSE_SLOW_QUERY_MS || '500');
        if (ms >= threshold) {
          const span = startSpan('db.query.slow');
          span.setTag('db.type', 'mongodb');
          span.setTag('db.duration_ms', String(ms));
          span.finish('ok');
        }
      });
    });
  } catch (_) {}
}

function _patchAxios() {
  try {
    const axios = require('axios');
    axios.interceptors.request.use(cfg => { cfg._pulseStart = Date.now(); return cfg; });
    axios.interceptors.response.use(
      res => {
        const ms = Date.now() - (res.config._pulseStart || Date.now());
        const threshold = parseInt(process.env.PULSE_SLOW_HTTP_MS || '2000');
        if (ms >= threshold || res.status >= 500) {
          const span = startSpan(`http.${(res.config.method||'get').toLowerCase()}`);
          span.setTag('http.url',      res.config.url || '');
          span.setTag('http.status',   String(res.status));
          span.setTag('http.duration', `${ms}ms`);
          if (res.status >= 500) span.setError(new Error(`HTTP ${res.status}`));
          span.finish(res.status >= 500 ? 'error' : 'ok');
        }
        return res;
      },
      err => {
        captureException(err);
        return Promise.reject(err);
      }
    );
  } catch (_) {}
}

function _patchFetch() {
  if (typeof globalThis.fetch !== 'function') return;
  const origFetch = globalThis.fetch;
  globalThis.fetch = async function(input, init) {
    const start = Date.now();
    try {
      const res = await origFetch(input, init);
      const ms  = Date.now() - start;
      const threshold = parseInt(process.env.PULSE_SLOW_HTTP_MS || '2000');
      if (ms >= threshold || res.status >= 500) {
        const span = startSpan(`http.${(init?.method || 'GET').toLowerCase()}`);
        span.setTag('http.url',      String(input));
        span.setTag('http.status',   String(res.status));
        span.setTag('http.duration', `${ms}ms`);
        if (res.status >= 500) span.setError(new Error(`HTTP ${res.status}`));
        span.finish(res.status >= 500 ? 'error' : 'ok');
      }
      return res;
    } catch (err) {
      captureException(err);
      throw err;
    }
  };
}

// ── Exception handlers ────────────────────────────────────────────────────────
function _installExceptionHandlers() {
  process.on('uncaughtException',    err => { captureException(err); });
  process.on('unhandledRejection',   err => { captureException(err instanceof Error ? err : new Error(String(err))); });
}

// ── Transport ─────────────────────────────────────────────────────────────────
function _queueLog(entry) {
  entry.node_id = entry.node_id || _nodeId;
  entry.service = entry.service || _service;
  entry.ts      = entry.ts || new Date().toISOString();
  _logQueue.push(entry);
  if (_logQueue.length > 5000) _logQueue.shift();
}

function _flush() {
  if (!_enabled) return;

  // Flush logs
  if (_logQueue.length > 0) {
    const batch = _logQueue.splice(0, 200);
    _post(`${_apiUrl}/api/ingest/logs/batch`, { node_id: _nodeId, service: _service, logs: batch });
  }

  // Flush spans
  for (const span of _spanQueue.splice(0, 100)) {
    _post(`${_apiUrl}/api/ingest/spans`, span);
  }
}

function _sendEvent(event) {
  setImmediate(() => _post(`${_apiUrl}/api/ingest/events`, event));
}

function _post(url, data) {
  try {
    const body     = JSON.stringify(data);
    const parsed   = new URL(url);
    const lib      = parsed.protocol === 'https:' ? https : http;
    const req      = lib.request({
      hostname: parsed.hostname,
      port:     parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path:     parsed.pathname,
      method:   'POST',
      headers:  { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    });
    req.on('error', () => {});
    req.setTimeout(5000, () => req.destroy());
    req.write(body);
    req.end();
  } catch (_) {}
}

// ── Exports ───────────────────────────────────────────────────────────────────
module.exports = {
  init,
  captureException, captureEvent,
  log, info, warn, error, debug,
  startSpan, withSpan, Span,
  expressMiddleware,
};
