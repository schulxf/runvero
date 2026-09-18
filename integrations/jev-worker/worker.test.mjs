import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { evaluateRequest, validateRequest } from './worker.mjs';

const ids = ['repeated_failure', 'environment_blocker', 'insufficient_evidence'];
function request() {
  return { protocol_version: 1, request_id: 'a'.repeat(32), model: 'typesafe-ai/jev',
    state: { attempts: [] }, timeout_ms: 1000,
    questions: Object.fromEntries(ids.map(id => [id, { type: 'boolean', instructions: 'Evidence only.' }])) };
}
function result(probability = 0.1) {
  return { answers: Object.fromEntries(ids.map(id => [id, { probability }])), headers: { secret: 'never forward' } };
}

test('forwards fixed model, explicit privacy option, no retries and abort signal', async () => {
  const response = await evaluateRequest(request(), async options => {
    assert.equal(options.model, 'typesafe-ai/jev');
    assert.equal(options.maxRetries, 0);
    assert.deepEqual(options.providerOptions, { gateway: { zeroDataRetention: true } });
    assert.ok(options.abortSignal instanceof AbortSignal);
    assert.equal('tools' in options, false);
    return result();
  });
  assert.deepEqual(Object.keys(response).sort(), ['answers', 'request_id']);
  assert.equal(response.request_id, 'a'.repeat(32));
  assert.equal(JSON.stringify(response).includes('never forward'), false);
});
for (const probability of [-1, 2, NaN, Infinity, true, '0.8', undefined]) {
  test(`rejects malformed probability ${String(probability)}`, async () => {
    await assert.rejects(evaluateRequest(request(), async () => ({ answers: Object.fromEntries(ids.map(id => [id, { probability }])) })), /Invalid observer answer/);
  });
}
test('rejects unknown model, question, and oversized input before evaluating', async () => {
  for (const input of [{ ...request(), model: 'other/model' },
    { ...request(), questions: { unknown: { type: 'boolean', instructions: '' } } },
    { ...request(), state: { value: 'x'.repeat(32_000) } },
    { ...request(), timeout_ms: 100_000 }]) {
    let called = false;
    await assert.rejects(evaluateRequest(input, async () => { called = true; return result(); }));
    assert.equal(called, false);
  }
});
test('valid request is accepted', () => assert.equal(validateRequest(request()).protocol_version, 1));
test('missing SDK/key does not leak errors or credentials to stdout', () => {
  const run = spawnSync(process.execPath, [fileURLToPath(new URL('./worker.mjs', import.meta.url))], {
    input: JSON.stringify(request()), encoding: 'utf8', env: {},
  });
  assert.equal(run.status, 2);
  assert.equal(run.stdout, '');
  assert.match(run.stderr, /observer unavailable/);
});
