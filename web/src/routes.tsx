import type { RouteObject } from "react-router";
import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { Compass } from "lucide-react";
import { Layout } from "./components/Layout";
import { EmptyState, ErrorPanel } from "./components/ui";
import { JobPage } from "./pages/JobPage";
import { JobsPage } from "./pages/JobsPage";
import { NewJobPage } from "./pages/NewJobPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <JobsPage /> },
      { path: "new", element: <NewJobPage /> },
      { path: "jobs/:jobId", element: <JobPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

function NotFound() {
  return (
    <EmptyState
      icon={<Compass className="size-7" />}
      title="Page not found"
      action={
        <Link to="/" className="text-sm font-medium text-amber-300 hover:text-amber-200">
          Back to jobs
        </Link>
      }
    >
      There's nothing at this address.
    </EmptyState>
  );
}

/** Shown if rendering a page throws: better than a blank screen. */
function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";
  return (
    <div className="mx-auto max-w-2xl p-8">
      <ErrorPanel title="Something broke on this page" message={message} />
    </div>
  );
}
