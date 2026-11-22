import type { Job } from "../api/client";

export type Stage = { key: string; label: string };

/** The worker's stages, in order (the AI step only when the job asked for it). */
export function stagesFor(job: Job): Stage[] {
  return [
    { key: "downloading", label: "Download" },
    { key: "transcribing", label: "Transcribe" },
    ...(job.request.ai ? [{ key: "asking AI", label: "AI picks" }] : []),
    { key: "detecting", label: "Find moments" },
    { key: "rendering", label: "Render clips" },
  ];
}

/** Index of the stage in progress: -1 before any has started, stages.length when all done. */
export function currentStageIndex(job: Job, stages: Stage[]): number {
  if (job.state === "done") return stages.length;
  if (job.state === "queued" || job.stage === null || job.stage === "starting") return -1;
  return stages.findIndex((stage) => stage.key === job.stage);
}

export const isActive = (job: Job): boolean => job.state === "queued" || job.state === "running";
