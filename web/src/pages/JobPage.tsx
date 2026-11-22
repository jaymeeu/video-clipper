import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, Clapperboard, ExternalLink, SearchX } from "lucide-react";
import { ApiError, type Job } from "../api/client";
import { ClipCard } from "../components/ClipCard";
import { StageProgress } from "../components/StageProgress";
import { EmptyState, ErrorPanel, Skeleton, StatusBadge } from "../components/ui";
import { useCreateJob, useJob, useNow } from "../hooks/jobs";
import { useDocumentTitle } from "../hooks/title";
import { elapsed, shortUrl, timeAgo } from "../lib/format";

export function JobPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  useDocumentTitle(job.data ? shortUrl(job.data.request.url, 32) : "Job");

  return (
    <div className="space-y-8">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200"
      >
        <ArrowLeft aria-hidden className="size-4" /> All jobs
      </Link>

      {job.isPending && <JobSkeleton />}

      {job.isError &&
        (job.error instanceof ApiError && job.error.status === 404 ? (
          <EmptyState icon={<SearchX className="size-7" />} title="Job not found">
            It may have expired: jobs and their clips are deleted after 7 days.
          </EmptyState>
        ) : (
          <ErrorPanel
            title="Couldn't load this job"
            message={job.error.message}
            onRetry={() => void job.refetch()}
            busy={job.isFetching}
          />
        ))}

      {job.data && <JobDetails job={job.data} />}
    </div>
  );
}

function JobDetails({ job }: { job: Job }) {
  const now = useNow(1000);
  const navigate = useNavigate();
  const retry = useCreateJob();
  const { request } = job;

  return (
    <>
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge state={job.state} />
          <span className="text-sm text-zinc-500">
            Started {timeAgo(job.created_at, now)}
            {job.state === "running" && ` · ${elapsed(job.created_at, now)} so far`}
          </span>
        </div>
        <h1 className="break-all text-xl font-semibold tracking-tight sm:text-2xl">
          <a
            href={request.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-2 hover:text-amber-200"
          >
            {shortUrl(request.url, 80)}
            <ExternalLink aria-hidden className="size-4 shrink-0 text-zinc-500" />
          </a>
        </h1>
        <ul className="flex flex-wrap gap-2 text-xs text-zinc-300">
          {[
            `${request.count} clips`,
            `~${request.duration}s each`,
            request.framing === "blur" ? "Blurred background" : "Fill the screen",
            request.captions ? "Captions" : "No captions",
            request.language ? `Language: ${request.language}` : "Language: auto",
            ...(request.ai ? ["AI picks"] : []),
          ].map((chip) => (
            <li key={chip} className="rounded-full bg-zinc-900 px-2.5 py-1 ring-1 ring-zinc-800">
              {chip}
            </li>
          ))}
        </ul>
      </header>

      {(job.state === "queued" || job.state === "running") && (
        <section
          aria-live="polite"
          className="space-y-4 rounded-2xl bg-zinc-900 p-5 ring-1 ring-zinc-800 sm:p-6"
        >
          <StageProgress job={job} />
          <p className="text-sm text-zinc-400">
            {job.state === "queued"
              ? "Waiting for a free worker. Videos are processed one at a time."
              : "This usually takes a few minutes, longer for long videos. You can leave this page: the job keeps running."}
          </p>
        </section>
      )}

      {job.state === "failed" && (
        <ErrorPanel
          title="This job failed"
          message={job.error ?? "Something went wrong."}
          retryLabel="Run it again"
          busy={retry.isPending}
          onRetry={() =>
            retry.mutate(job.request, { onSuccess: (next) => navigate(`/jobs/${next.id}`) })
          }
        />
      )}

      {job.state === "done" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold">
              {job.clips.length === 1 ? "1 clip" : `${job.clips.length} clips`}
            </h2>
            <p className="text-sm text-zinc-500">
              Best first · finished {timeAgo(job.updated_at, now)}
              {job.failed_clips > 0 && (
                <span className="text-amber-300">
                  {" "}
                  · {job.failed_clips} more couldn't be rendered
                </span>
              )}
            </p>
          </div>
          {job.clips.length === 0 ? (
            <EmptyState icon={<Clapperboard className="size-7" />} title="No clips">
              Nothing in this video stood out enough to clip.
            </EmptyState>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {job.clips.map((clip, i) => (
                <ClipCard key={clip.filename} jobId={job.id} clip={clip} rank={i + 1} />
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
}

function JobSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-6 w-24 rounded-full" />
      <Skeleton className="h-8 w-3/4" />
      <div className="grid grid-cols-1 gap-5 pt-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="aspect-[9/16] rounded-2xl" />
        ))}
      </div>
    </div>
  );
}
