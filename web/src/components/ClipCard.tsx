import { useState } from "react";
import { Download, Sparkles } from "lucide-react";
import { clipUrl, type Clip } from "../api/client";
import { clock, length, reasonParts } from "../lib/format";

/** One finished clip: a 9:16 player, what it is, why it was picked, and a download button. */
export function ClipCard({ jobId, clip, rank }: { jobId: string; clip: Clip; rank: number }) {
  const [showWhy, setShowWhy] = useState(false);
  const src = clipUrl(jobId, clip.filename);
  const title = clip.title || `Moment at ${clock(clip.start)}`;
  const reasons = reasonParts(clip.reason);

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl bg-zinc-900 ring-1 ring-zinc-800 transition hover:ring-zinc-700">
      <div className="relative aspect-[9/16] bg-black">
        <video
          // "#t=0.1" makes the browser show a real frame as the poster instead of black.
          src={`${src}#t=0.1`}
          controls
          playsInline
          preload="metadata"
          aria-label={`Clip ${rank}: ${title}`}
          className="h-full w-full object-contain"
          onPlay={(e) => pauseOtherVideos(e.currentTarget)}
        />
        <span className="pointer-events-none absolute top-3 left-3 rounded-md bg-black/70 px-2 py-0.5 text-xs font-semibold text-white backdrop-blur">
          #{rank}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <h3 className="line-clamp-2 font-semibold leading-snug">{title}</h3>
          <p className="mt-1 text-sm text-zinc-400">
            {/* Untitled clips already show the time in their title: don't repeat it. */}
            {clip.title
              ? `From ${clock(clip.start)} · ${length(clip.duration)}`
              : `${length(clip.duration)} long`}
          </p>
        </div>

        {reasons.length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowWhy((v) => !v)}
              aria-expanded={showWhy}
              className="inline-flex items-center gap-1.5 text-sm text-amber-300 hover:text-amber-200"
            >
              <Sparkles aria-hidden className="size-3.5" />
              {showWhy ? "Hide why" : "Why this clip?"}
            </button>
            {showWhy && (
              <ul className="mt-2 space-y-1.5 text-sm text-zinc-300">
                {reasons.map((reason) => (
                  <li key={reason} className="rounded-lg bg-zinc-800/60 px-3 py-2">
                    {reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <a
          href={src}
          download={clip.filename}
          className="mt-auto inline-flex items-center justify-center gap-2 rounded-xl bg-amber-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-amber-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
        >
          <Download aria-hidden className="size-4" />
          Download
        </a>
      </div>
    </article>
  );
}

/** Only one clip plays at a time. */
function pauseOtherVideos(playing: HTMLVideoElement) {
  document.querySelectorAll("video").forEach((video) => {
    if (video !== playing) video.pause();
  });
}
