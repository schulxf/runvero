/** One bounded, advisory-only request. No tools, shell, files or action executor. */
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const MAX_BYTES = 32_000;
const IDS = ['environment_blocker', 'insufficient_evidence', 'repeated_failure'];

export function validateRequest(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request) ||
      Buffer.byteLength(JSON.stringify(request)) > MAX_BYTES ||
      request.protocol_version !== 1 || request.model !== 'typesafe-ai/jev' ||
      !/^[a-f0-9]{32}$/.test(request.request_id ?? '') ||
      !Number.isInteger(request.timeout_ms) || request.timeout_ms < 1000 || request.timeout_ms > 30_000 ||
      !request.state || typeof request.state !== 'object' || Array.isArray(request.state) ||
      !request.questions || Object.keys(request.questions).sort().join() !== IDS.join()) {
    throw new Error('Invalid observer request');
  }
  for (const question of Object.values(request.questions)) {
    if (question?.type !== 'boolean' || typeof question.instructions !== 'string' ||
        question.instructions.length > 1500) throw new Error('Invalid observer question');
  }
  return request;
}

export async function evaluateRequest(input, evaluate) {
  const request = validateRequest(input);
  const result = await evaluate({
    model: 'typesafe-ai/jev',
    state: request.state,
    questions: request.questions,
    abortSignal: AbortSignal.timeout(request.timeout_ms),
    maxRetries: 0,
    providerOptions: { gateway: { zeroDataRetention: true } },
  });
  const answers = {};
  for (const id of IDS) {
    const probability = result?.answers?.[id]?.probability;
    if (typeof probability !== 'number' || !Number.isFinite(probability) || probability < 0 || probability > 1) {
      throw new Error('Invalid observer answer');
    }
    answers[id] = { probability };
  }
  // Whitelist fields. Never forward SDK headers, errors, request bodies or metadata.
  return { request_id: request.request_id, answers };
}

async function main() {
  try {
    if (!process.env.AI_GATEWAY_API_KEY) throw new Error('Missing credential');
    const chunks = [];
    let size = 0;
    for await (const chunk of process.stdin) {
      size += chunk.length;
      if (size > MAX_BYTES) throw new Error('Request too large');
      chunks.push(chunk);
    }
    const request = validateRequest(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    // Lazy import keeps offline protocol tests independent of npm/API access.
    const { experimental_evaluate: evaluate } = await import('ai');
    if (typeof evaluate !== 'function') throw new Error('Unsupported SDK');
    const result = await evaluateRequest(request, evaluate);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch {
    process.stderr.write('Jev observer unavailable; no action was executed.\n');
    process.exitCode = 2;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
