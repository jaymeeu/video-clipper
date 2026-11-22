/**
 * Data hooks (TanStack Query ≈ a cache + fetch state machine).
 * Polling is automatic while a job is queued or running, and stops by itself afterwards.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, createJob, getJob, listJobs, type Job } from "../api/client";
import { isActive } from "../lib/stages";

const LIST_POLL_MS = 3000;
const JOB_POLL_MS = 2000;

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: () => listJobs(),
    refetchInterval: (query) => (query.state.data?.some(isActive) ? LIST_POLL_MS : false),
  });
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (query) =>
      query.state.data && isActive(query.state.data) ? JOB_POLL_MS : false,
    // A missing job won't appear by retrying.
    retry: (failures, error) =>
      !(error instanceof ApiError && error.status === 404) && failures < 2,
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createJob,
    onSuccess: (job: Job) => {
      queryClient.setQueryData(["job", job.id], job); // the job page renders instantly
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

/** Re-render every `ms`, so "5 minutes ago" and elapsed timers stay current. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
