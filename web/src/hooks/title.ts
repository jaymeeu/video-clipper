import { useEffect } from "react";

/** Set the browser tab title for a page: "Jobs · clippers". */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · clippers` : "clippers";
  }, [title]);
}
