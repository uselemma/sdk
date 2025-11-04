import { Tracer, SpanType, TraceRunner } from "./src/index";

// Example functions to trace
async function fetchUserData(userId: string) {
  // Simulate API call
  await new Promise((resolve) => setTimeout(resolve, 100));
  return { id: userId, name: "John Doe", email: "john@example.com" };
}

async function processData(data: any) {
  // Simulate data processing
  await new Promise((resolve) => setTimeout(resolve, 50));
  return { ...data, processed: true, timestamp: Date.now() };
}

function calculateScore(userData: any) {
  // Simulate synchronous calculation
  return Math.floor(Math.random() * 100);
}

async function main() {
  console.log("Starting trace example with TraceRunner...\n");

  // Create a tracer
  const tracer = new Tracer("example-service");

  // Create a TraceRunner with optional candidate prompts
  const candidatePrompts = {
    "greeting-prompt": "Hi {{ name }}, you scored {{ score }} points!",
  };
  const traceRunner = new TraceRunner(tracer, candidatePrompts);

  // Create a root operation that will establish the trace context
  async function runWorkflow() {
    // Wrap functions with tracing
    const tracedFetchUserData = tracer.wrap(SpanType.AGENT, fetchUserData);
    const tracedProcessData = tracer.wrap(SpanType.NODE, processData);
    const tracedCalculateScore = tracer.wrap(SpanType.TOOL, calculateScore);

    // Execute traced operations
    const userData = await tracedFetchUserData("user-123");
    console.log("Fetched user data:", userData);

    // Add metadata to current span
    tracer.addMetadata("user.id", userData.id);
    tracer.addMetadata("user.name", userData.name);

    const processedData = await tracedProcessData(userData);
    console.log("Processed data:", processedData);

    // Add an event
    tracer.addEvent("data_processing_complete", {
      record_count: 1,
      success: true,
    });

    const score = tracedCalculateScore(processedData);
    console.log("Calculated score:", score);

    // Example with prompt tracing
    const promptContext = tracer.startPrompt(
      "greeting-prompt",
      "Hello {{ name }}, your score is {{ score }}!",
      { name: userData.name, score }
    );

    console.log("\nRendered prompt:", promptContext.renderedPrompt);
    console.log("(Note: Candidate prompt override was applied if configured)");

    // Simulate LLM call
    await new Promise((resolve) => setTimeout(resolve, 200));
    const llmResponse = `Great job, ${userData.name}! Your score of ${score} is excellent.`;

    // Add LLM output with metadata
    tracer.addLLMOutput(llmResponse, "gpt-4", {
      prompt_tokens: 25,
      completion_tokens: 15,
      total_tokens: 40,
    });

    promptContext.end();
  }

  // Wrap the root workflow to establish trace context
  const tracedWorkflow = tracer.wrap(SpanType.AGENT, runWorkflow);

  // Run your traced code within the TraceRunner context
  await traceRunner.run(async () => {
    await tracedWorkflow();
  });

  // Record the trace data - this flushes spans and collects them
  const traceData = await traceRunner.record();

  console.log("\n=== Trace Summary ===");
  console.log("Trace ID:", traceData.trace_id);
  console.log(`Total spans collected: ${traceData.spans.length}\n`);

  // Print detailed span information
  traceData.spans.forEach((span, index) => {
    console.log(`--- Span ${index + 1} ---`);
    console.log("Name:", span.name);
    console.log("Span ID:", span.span_id);
    console.log("Parent Span ID:", span.parent_span_id || "none (root span)");
    console.log(
      "Duration:",
      span.duration_ms ? `${span.duration_ms.toFixed(2)}ms` : "N/A"
    );
    console.log("Status:", span.status?.status_code || "UNSET");

    if (span.attributes && Object.keys(span.attributes).length > 0) {
      console.log("Attributes:");
      for (const [key, value] of Object.entries(span.attributes)) {
        const displayValue =
          typeof value === "string" && value.length > 100
            ? value.substring(0, 100) + "..."
            : value;
        console.log(`  ${key}:`, displayValue);
      }
    }

    if (span.events && span.events.length > 0) {
      console.log("Events:");
      span.events.forEach((event) => {
        console.log(`  - ${event.name}`, event.attributes || "");
      });
    }
    console.log();
  });
}

main().catch(console.error);
