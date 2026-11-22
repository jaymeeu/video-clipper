import { Check } from "lucide-react";
import type { Job } from "../api/client";
import { currentStageIndex, stagesFor } from "../lib/stages";
import { cx, Spinner } from "./ui";

/** The worker's progress as a row of steps: done ✓, in progress (spinner), still to come. */
export function StageProgress({ job }: { job: Job }) {
  const stages = stagesFor(job);
  const current = currentStageIndex(job, stages);

  return (
    <ol aria-label="Progress" className="flex flex-wrap items-center gap-x-2 gap-y-3">
      {stages.map((stage, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={stage.key} className="flex items-center gap-2">
            <span
              aria-current={active ? "step" : undefined}
              className={cx(
                "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm ring-1 ring-inset",
                done && "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
                active && "bg-amber-400/10 text-amber-200 ring-amber-400/40",
                !done && !active && "text-zinc-500 ring-zinc-800",
              )}
            >
              {done && <Check aria-hidden className="size-3.5" />}
              {active && <Spinner className="size-3.5" />}
              {stage.label}
            </span>
            {i < stages.length - 1 && (
              <span
                aria-hidden
                className={cx("h-px w-4", done ? "bg-emerald-400/40" : "bg-zinc-800")}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
