import { Link } from "react-router";
import { ChevronRight, Film, Plus } from "lucide-react";
import type { Job } from "../api/client";
import { EmptyState, ErrorPanel, Skeleton, StatusBadge } from "../components/ui";
import { useDocumentTitle } from "../hooks/title";
import { useJobs, useNow } from "../hooks/jobs";
import { shortUrl, timeAgo } from "../lib/format";
import { isActive, stagesFor } from "../lib/stages";

export function JobsPage() {
  useDocumentTitle("Jobs");
  const jobs = useJobs();
  const now = useNow(30_000);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Every video you've sent for clipping. Jobs and their clips are kept for 7 days.
          </p>
        </div>
        {jobs.data?.some(isActive) && (
          <span className="flex items-center gap-2 text-xs text-zinc-400">
            <span className="size-2 animate-pulse rounded-full bg-amber-400" /> Updating live
          </span>
        )}
      </div>

      {jobs.isPending && <JobsSkeleton />}

      {jobs.isError && (
        <ErrorPanel
          title="Couldn't load jobs"
          message={jobs.error.message}
          onRetry={() => void jobs.refetch()}
          busy={jobs.isFetching}
        />
      )}

      {jobs.data?.length === 0 && (
        <EmptyState
          icon={<Film className="size-7" />}
          title="No clips yet"
          action={
            <Link
              to="/new"
              className="inline-flex items-center gap-1.5 rounded-xl bg-amber-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-amber-300"
            >
              <Plus aria-hidden className="size-4" /> Make your first clips
            </Link>
          }
        >
          Paste a link to a stream recording or any video, and we'll find the best moments and turn
          them into captioned vertical clips.
        </EmptyState>
      )}

      {jobs.data && jobs.data.length > 0 && (
        <ul className="divide-y divide-zinc-800/80 overflow-hidden rounded-2xl bg-zinc-900 ring-1 ring-zinc-800">
          {jobs.data.map((job) => (
            <li key={job.id}>
              <JobRow job={job} now={now} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function JobRow({ job, now }: { job: Job; now: number }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-zinc-800/50 focus-visible:bg-zinc-800/50 focus-visible:outline-none sm:px-5"
    >
      <div className="w-24 shrink-0">
        <StatusBadge state={job.state} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={job.request.url}>
          {shortUrl(job.request.url, 64)}
        </p>
        <p className="mt-0.5 truncate text-sm text-zinc-400">{summary(job)}</p>
      </div>
      <time dateTime={job.created_at} className="hidden shrink-0 text-sm text-zinc-500 sm:block">
        {timeAgo(job.created_at, now)}
      </time>
      <ChevronRight aria-hidden className="size-4 shrink-0 text-zinc-600" />
    </Link>
  );
}

function summary(job: Job): string {
  switch (job.state) {
    case "queued":
      return "Waiting for a worker…";
    case "running": {
      const stage = stagesFor(job).find((s) => s.key === job.stage);
      return stage ? `${stage.label}…` : "Starting…";
    }
    case "done":
      return job.clips.length === 1 ? "1 clip ready" : `${job.clips.length} clips ready`;
    case "failed":
      return job.error ?? "Something went wrong";
  }
}

function JobsSkeleton() {
  return (
    <div className="space-y-px overflow-hidden rounded-2xl ring-1 ring-zinc-800">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-4 bg-zinc-900 px-5 py-4">
          <Skeleton className="h-6 w-20 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
