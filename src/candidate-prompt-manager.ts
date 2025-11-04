import { AsyncLocalStorage } from "node:async_hooks";

/**
 * Manages candidate prompt overrides using AsyncLocalStorage for context-local state.
 */
export class CandidatePromptManager {
  private readonly _overrides: AsyncLocalStorage<Record<string, string> | null>;

  constructor() {
    this._overrides = new AsyncLocalStorage<Record<string, string> | null>();
  }

  /**
   * Runs a callback with candidate prompts set in the async context.
   *
   * @param candidatePrompts - Optional dictionary of prompt name -> candidate template
   * @param callback - Function to run with the context
   * @returns Result of the callback
   */
  async run<T>(
    candidatePrompts: Record<string, string> | null | undefined,
    callback: () => Promise<T> | T
  ): Promise<T> {
    return this._overrides.run(candidatePrompts ?? null, callback);
  }

  /**
   * Get the effective template, applying candidate override if present.
   *
   * @param promptName - Name of the prompt
   * @param defaultTemplate - Default template to use if no override
   * @returns Tuple of [effectiveTemplate, overrideApplied]
   */
  getEffectiveTemplate(
    promptName: string,
    defaultTemplate: string
  ): [string, boolean] {
    const overrides = this._overrides.getStore();
    if (overrides && promptName in overrides) {
      return [overrides[promptName], true];
    }
    return [defaultTemplate, false];
  }

  /**
   * Annotate span with candidate prompt metadata.
   *
   * @param span - OpenTelemetry span to annotate
   */
  annotateSpan(span: {
    setAttribute: (key: string, value: unknown) => void;
  }): void {
    const overrides = this._overrides.getStore();
    if (overrides !== null && overrides !== undefined) {
      try {
        span.setAttribute(
          "candidate_prompts.count",
          Object.keys(overrides).length
        );
      } catch {
        // Best-effort; avoid breaking tracing on attribute errors
      }
    }
  }
}
