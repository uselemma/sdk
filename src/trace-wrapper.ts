import { context, trace, Span } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";

export type TraceContext = {
  span: Span;
  runId: string;
  onComplete: (result: unknown) => void;
  onError: (error: unknown) => void;
  recordGenerationResults: (results: Record<string, string>) => void;
};

export function wrapAgent<A extends unknown[]>(agentName: string, options: { isExperiment?: boolean, initialState?: any, endOnExit?: boolean }, fn: (traceContext: TraceContext, ...args: A) => any) {
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
        const onComplete = (result: unknown) => {
          span.setAttribute("lemma.agent.output", JSON.stringify(result));
          span.end();
        };

        const onError = (error: unknown) => {
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 });
          span.end();
        };

        const recordGenerationResults = (results: Record<string, string>) => {
          span.setAttribute("lemma.agent.generation_results", JSON.stringify(results));
        };

        const result = await fn.call(this, { span, runId, onComplete, onError, recordGenerationResults }, ...args);

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
