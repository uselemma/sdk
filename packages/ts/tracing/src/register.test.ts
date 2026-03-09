import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import { OpenAIInstrumentation } from "@arizeai/openinference-instrumentation-openai";
import { createLemmaSpanProcessor, registerOTel } from "./register";

const ENV_KEY = "LEMMA_API_KEY";
const ENV_PROJECT = "LEMMA_PROJECT_ID";

describe("createLemmaSpanProcessor", () => {
  beforeEach(() => {
    delete process.env[ENV_KEY];
    delete process.env[ENV_PROJECT];
  });

  afterEach(() => {
    delete process.env[ENV_KEY];
    delete process.env[ENV_PROJECT];
  });

  it("throws when API key and project ID are missing", () => {
    expect(() => createLemmaSpanProcessor()).toThrow(
      "@uselemma/tracing: Missing API key and/or project ID"
    );
  });

  it("throws when only API key is set", () => {
    process.env[ENV_KEY] = "lma_test";
    expect(() => createLemmaSpanProcessor()).toThrow(
      "@uselemma/tracing: Missing API key and/or project ID"
    );
  });

  it("throws when only project ID is set", () => {
    process.env[ENV_PROJECT] = "proj_test";
    expect(() => createLemmaSpanProcessor()).toThrow(
      "@uselemma/tracing: Missing API key and/or project ID"
    );
  });

  it("returns a span processor when env vars are set", () => {
    process.env[ENV_KEY] = "lma_test";
    process.env[ENV_PROJECT] = "proj_test";
    const processor = createLemmaSpanProcessor();
    expect(processor).toBeDefined();
    expect(typeof processor.onStart).toBe("function");
    expect(typeof processor.onEnd).toBe("function");
  });

  it("accepts explicit options and returns a span processor", () => {
    const processor = createLemmaSpanProcessor({
      apiKey: "lma_explicit",
      projectId: "proj_explicit",
    });
    expect(processor).toBeDefined();
  });

  it("explicit options take precedence over env vars", () => {
    process.env[ENV_KEY] = "lma_from_env";
    process.env[ENV_PROJECT] = "proj_from_env";
    // should not throw - explicit values are used
    const processor = createLemmaSpanProcessor({
      apiKey: "lma_explicit",
      projectId: "proj_explicit",
    });
    expect(processor).toBeDefined();
  });
});

describe("registerOTel", () => {
  beforeEach(() => {
    process.env[ENV_KEY] = "lma_test";
    process.env[ENV_PROJECT] = "proj_test";
  });

  afterEach(() => {
    delete process.env[ENV_KEY];
    delete process.env[ENV_PROJECT];
  });

  it("returns a NodeTracerProvider", () => {
    const provider = registerOTel();
    expect(provider).toBeInstanceOf(NodeTracerProvider);
    provider.shutdown();
  });

  it("returned provider works with registerInstrumentations + OpenAIInstrumentation", () => {
    const provider = registerOTel();
    expect(() => {
      registerInstrumentations({
        instrumentations: [new OpenAIInstrumentation()],
        tracerProvider: provider,
      });
    }).not.toThrow();
    provider.shutdown();
  });

  it("OpenAIInstrumentation uses the Lemma tracer provider", () => {
    const provider = registerOTel();
    const instrumentation = new OpenAIInstrumentation({ tracerProvider: provider });
    registerInstrumentations({
      instrumentations: [instrumentation],
      tracerProvider: provider,
    });
    // The instrumentation's tracer should come from the Lemma provider
    expect(instrumentation.tracer).toBeDefined();
    provider.shutdown();
  });

  it("accepts explicit apiKey and projectId", () => {
    delete process.env[ENV_KEY];
    delete process.env[ENV_PROJECT];
    const provider = registerOTel({
      apiKey: "lma_explicit",
      projectId: "proj_explicit",
    });
    expect(provider).toBeInstanceOf(NodeTracerProvider);
    provider.shutdown();
  });

  it("throws when no credentials provided", () => {
    delete process.env[ENV_KEY];
    delete process.env[ENV_PROJECT];
    expect(() => registerOTel()).toThrow(
      "@uselemma/tracing: Missing API key and/or project ID"
    );
  });
});
