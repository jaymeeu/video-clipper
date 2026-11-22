import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { ClipboardPaste, Scissors } from "lucide-react";
import { ApiError, type Framing, type JobRequest } from "../api/client";
import { cx, ErrorPanel, Segmented, Spinner, Toggle } from "../components/ui";
import { useCreateJob } from "../hooks/jobs";
import { useDocumentTitle } from "../hooks/title";
import { isWebUrl } from "../lib/format";

const COUNTS = [3, 5, 8, 10].map((n) => ({ value: n, label: String(n) }));
const LENGTHS = [15, 30, 45, 60].map((n) => ({ value: n, label: `${n}s` }));
const LANGUAGES = [
  { value: "", label: "Detect automatically" },
  { value: "en", label: "English (and Pidgin)" },
  { value: "yo", label: "Yoruba" },
  { value: "ha", label: "Hausa" },
  { value: "fr", label: "French" },
];

export function NewJobPage() {
  useDocumentTitle("New clips");
  const navigate = useNavigate();
  const createJob = useCreateJob();

  const [url, setUrl] = useState("");
  const [urlTouched, setUrlTouched] = useState(false);
  const [count, setCount] = useState(5);
  const [duration, setDuration] = useState(30);
  const [framing, setFraming] = useState<Framing>("blur");
  const [captions, setCaptions] = useState(true);
  const [language, setLanguage] = useState("");
  const [ai, setAi] = useState(false);

  const urlProblem = !url.trim()
    ? "Paste the link to a video."
    : isWebUrl(url)
      ? null
      : "That doesn't look like a web link (it should start with https://).";
  const serverError = createJob.error instanceof ApiError ? createJob.error : null;
  const urlError =
    (urlTouched && urlProblem) || (serverError?.field === "url" ? serverError.message : null);

  async function pasteFromClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setUrl(text.trim());
    } catch {
      // Clipboard access denied: the user can still paste with Cmd/Ctrl+V.
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setUrlTouched(true);
    if (urlProblem) return;
    const body: JobRequest = {
      url: url.trim(),
      count,
      duration,
      framing,
      captions,
      ai,
      language: language || null,
    };
    createJob.mutate(body, { onSuccess: (job) => navigate(`/jobs/${job.id}`) });
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">New clips</h1>
      <p className="mt-1 text-sm text-zinc-400">
        We'll find the best moments, frame them for phones and add captions.
      </p>

      <form onSubmit={submit} noValidate className="mt-8 space-y-6">
        <section className="rounded-2xl bg-zinc-900 p-5 ring-1 ring-zinc-800 sm:p-6">
          <label htmlFor="url" className="block text-sm font-medium">
            Video link
          </label>
          <p className="mt-0.5 text-sm text-zinc-400">
            A stream recording, a direct .mp4 link, or a YouTube/Twitch page.
          </p>
          <div className="mt-3 flex gap-2">
            <input
              id="url"
              type="url"
              inputMode="url"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              placeholder="https://…"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (serverError) createJob.reset();
              }}
              onBlur={() => setUrlTouched(true)}
              aria-invalid={Boolean(urlError)}
              aria-describedby={urlError ? "url-error" : undefined}
              className={cx(
                "min-w-0 flex-1 rounded-xl bg-zinc-950 px-4 py-3 text-base ring-1 placeholder:text-zinc-600 focus:outline-none focus:ring-2",
                urlError
                  ? "ring-red-500/60 focus:ring-red-400"
                  : "ring-zinc-800 focus:ring-amber-300",
              )}
            />
            <button
              type="button"
              onClick={() => void pasteFromClipboard()}
              className="inline-flex shrink-0 items-center gap-2 rounded-xl px-3.5 text-sm font-medium text-zinc-300 ring-1 ring-zinc-800 hover:bg-zinc-800 hover:text-white"
            >
              <ClipboardPaste aria-hidden className="size-4" />
              <span className="hidden sm:inline">Paste</span>
            </button>
          </div>
          {urlError && (
            <p id="url-error" role="alert" className="mt-2 text-sm text-red-300">
              {urlError}
            </p>
          )}
        </section>

        <section className="space-y-6 rounded-2xl bg-zinc-900 p-5 ring-1 ring-zinc-800 sm:p-6">
          <div className="grid gap-6 sm:grid-cols-2">
            <Field
              label="How many clips"
              hint="Fewer if the video doesn't have that many good moments."
            >
              <Segmented
                name="Number of clips"
                value={count}
                options={COUNTS}
                onChange={setCount}
              />
            </Field>
            <Field label="Clip length" hint="Roughly: clips end at a natural pause.">
              <Segmented
                name="Clip length"
                value={duration}
                options={LENGTHS}
                onChange={setDuration}
              />
            </Field>
          </div>

          <Field label="Framing">
            <div role="radiogroup" aria-label="Framing" className="grid grid-cols-2 gap-3">
              <FramingOption
                value="blur"
                current={framing}
                onChange={setFraming}
                title="Blurred background"
                description="Whole picture, larger in the middle"
              />
              <FramingOption
                value="crop"
                current={framing}
                onChange={setFraming}
                title="Fill the screen"
                description="Zoomed in, sides cut off"
              />
            </div>
          </Field>

          <Field label="Spoken language" htmlFor="language">
            <select
              id="language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-xl bg-zinc-950 px-3.5 py-2.5 text-sm ring-1 ring-zinc-800 focus:outline-none focus:ring-2 focus:ring-amber-300 sm:w-72"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </Field>

          <div className="space-y-5 border-t border-zinc-800 pt-6">
            <Toggle
              checked={captions}
              onChange={setCaptions}
              label="Captions"
              description="Burned in, with each word lighting up as it's spoken."
            />
            <Toggle
              checked={ai}
              onChange={setAi}
              label="AI picks"
              description="An AI model also reads what's said to find jokes, hot takes and big moments, and names each clip. Sends the transcript to OpenAI (about 1¢ per video)."
            />
          </div>
        </section>

        {serverError && serverError.field !== "url" && (
          <ErrorPanel title="Couldn't start the job" message={serverError.message} />
        )}

        <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-zinc-400">
            Up to {count} clips of about {duration}s{ai ? ", picked with AI" : ""}.
          </p>
          <button
            type="submit"
            disabled={createJob.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-400 px-6 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-amber-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:opacity-70"
          >
            {createJob.isPending ? <Spinner /> : <Scissors aria-hidden className="size-4" />}
            {createJob.isPending ? "Starting…" : "Make clips"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div>
      {htmlFor ? (
        <label htmlFor={htmlFor} className="mb-2 block text-sm font-medium">
          {label}
        </label>
      ) : (
        <p className="mb-2 text-sm font-medium">{label}</p>
      )}
      {children}
      {hint && <p className="mt-2 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

function FramingOption({
  value,
  current,
  onChange,
  title,
  description,
}: {
  value: Framing;
  current: Framing;
  onChange: (value: Framing) => void;
  title: string;
  description: string;
}) {
  const selected = value === current;
  return (
    <label
      className={cx(
        "flex cursor-pointer items-center gap-4 rounded-xl p-3 ring-1 transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-amber-300",
        selected ? "bg-amber-400/5 ring-amber-400/60" : "ring-zinc-800 hover:ring-zinc-700",
      )}
    >
      <input
        type="radio"
        name="framing"
        className="sr-only"
        checked={selected}
        onChange={() => onChange(value)}
      />
      <FramingPreview kind={value} />
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="mt-0.5 block text-xs text-zinc-400">{description}</span>
      </span>
    </label>
  );
}

/** A tiny phone-shaped sketch of each framing mode. */
function FramingPreview({ kind }: { kind: Framing }) {
  return (
    <svg viewBox="0 0 36 64" className="h-16 w-9 shrink-0" aria-hidden>
      <rect width="36" height="64" rx="5" className="fill-zinc-800" />
      {kind === "blur" ? (
        <>
          <rect x="2" y="2" width="32" height="60" rx="4" className="fill-zinc-700/70" />
          <rect x="2" y="13" width="32" height="38" rx="1" className="fill-amber-400/80" />
        </>
      ) : (
        <rect x="2" y="2" width="32" height="60" rx="4" className="fill-amber-400/80" />
      )}
      <rect x="8" y="44" width="20" height="3" rx="1.5" className="fill-white/90" />
    </svg>
  );
}
