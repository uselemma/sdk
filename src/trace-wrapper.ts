import { context, trace } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";

export async function wrapAgent<A extends unknown[], F extends (...args: A) => ReturnType<F>>(agentName: string, initialState: any, fn: F, ...args: A) {
  const tracer = trace.getTracer("lemma");

  const runId = uuidv4();
  const span = tracer.startSpan(agentName, {
    attributes: {
      "lemma.agent.run_id": runId,
      "lemma.agent.input": initialState,
    },
  });

  const ctx = trace.setSpan(context.active(), span);

  try {
    return await context.with(ctx, async () => {
      const result = await fn(...args);
      span.end();
      return { result, runId };
    });
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: 2 });
    span.end();
    throw err;
  }
}