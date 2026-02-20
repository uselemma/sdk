export {
  registerOTel,
  createLemmaSpanProcessor,
  type LemmaOTelOptions,
  type RegisterOTelOptions,
  type CreateLemmaSpanProcessorOptions,
} from "./register";
export {
  enableExperimentMode,
  disableExperimentMode,
  isExperimentModeEnabled,
} from "./experiment-mode";
export { wrapAgent, type TraceContext } from "./trace-wrapper";
