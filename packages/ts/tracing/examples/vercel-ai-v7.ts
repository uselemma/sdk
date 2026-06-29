import { generateText } from "ai";
import { Lemma, vercelAI } from "@uselemma/tracing";

const lemma = new Lemma({
  apiKey: process.env.LEMMA_API_KEY,
  projectId: process.env.LEMMA_PROJECT_ID,
});

export async function runVercelAIV7(
  model: Parameters<typeof generateText>[0]["model"],
  userMessage: string,
) {
  const trace = lemma.trace({
    name: "support-agent",
    input: userMessage,
  });

  const result = await generateText({
    model,
    prompt: userMessage,
    telemetry: {
      integrations: [vercelAI({ trace })],
    },
  });

  return result.text;
}
