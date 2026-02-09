import { context, trace } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";

export function wrapAgent<A extends unknown[], F extends (...args: A) => ReturnType<F>>(agentName: string, options: { isExperiment?: boolean, initialState?: any, endOnExit?: boolean }, fn: F) {
  const wrappedFunction = async function (this: any, ...args: A) {
    const tracer = trace.getTracer("lemma");

    const runId = uuidv4();
    const span = tracer.startSpan(agentName, {
      attributes: {
        "lemma.agent.run_id": runId,
        "lemma.agent.input": JSON.stringify(options.initialState),
        "lemma.agent.is_experiment": options.isExperiment,
      },
    });

    const ctx = trace.setSpan(context.active(), span);

    try {
      return await context.with(ctx, async () => {
        const result = await fn.apply(this, args);

        if (options?.endOnExit !== false) {
          span.end();
        }

        return { result, runId, span };
      });
    } catch (err) {
      span.recordException(err as Error);
      span.setStatus({ code: 2 });

      if (options?.endOnExit !== false) {
        span.end();
      }

      throw err;
    }
  };

  return wrappedFunction;
}
