import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";

export type RegisterOTelOptions = {
  /** Lemma API key. Defaults to LEMMA_API_KEY environment variable. */
  apiKey?: string;
  /** Lemma project ID. Defaults to LEMMA_PROJECT_ID environment variable. */
  projectId?: string;
  /** Base URL for the Lemma API. Defaults to https://api.uselemma.ai */
  baseUrl?: string;
};

/**
 * Registers an OpenTelemetry tracer provider configured to send traces to Lemma.
 *
 * This is a convenience wrapper that sets up `NodeTracerProvider` with a
 * `BatchSpanProcessor` and `OTLPTraceExporter` pointing at the Lemma ingest endpoint.
 *
 * @example
 * // instrumentation.ts (Next.js)
 * export async function register() {
 *   if (process.env.NEXT_RUNTIME === 'nodejs') {
 *     const { registerOTel } = await import('@uselemma/tracing');
 *     registerOTel();
 *   }
 * }
 *
 * @example
 * // With explicit options
 * registerOTel({
 *   apiKey: 'lma_...',
 *   projectId: 'proj_...',
 * });
 */
export function registerOTel(options: RegisterOTelOptions = {}) {
  // Resolve options, falling back to environment variables / defaults
  const apiKey = options.apiKey ?? process.env.LEMMA_API_KEY;
  const projectId = options.projectId ?? process.env.LEMMA_PROJECT_ID;
  const baseUrl = options.baseUrl ?? "https://api.uselemma.ai";

  // Fail fast if required credentials are missing
  if (!apiKey || !projectId) {
    throw new Error(
      "@uselemma/tracing: Missing API key and/or project ID. Set the LEMMA_API_KEY and LEMMA_PROJECT_ID environment variables or pass them to registerOTel()."
    );
  }

  // Create a Node tracer provider with a batch processor that exports
  // spans to the Lemma OTLP ingest endpoint over HTTP/protobuf
  const tracerProvider = new NodeTracerProvider({
    spanProcessors: [
      new BatchSpanProcessor(
        new OTLPTraceExporter({
          url: `${baseUrl}/otel/v1/traces`,
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "X-Lemma-Project-ID": projectId,
          },
        })
      ),
    ],
  });

  // Register this provider as the global tracer provider so all
  // subsequent `trace.getTracer()` calls use it
  tracerProvider.register();

  return tracerProvider;
}
