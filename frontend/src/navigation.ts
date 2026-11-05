import { useCallback, useEffect, useState, type MouseEvent } from "react";

// Keep native browser history and React route state synchronized without a router dependency.
export function useNavigation() {
  const [path, setPath] = useState(location.pathname+location.search+location.hash);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    // Browser Back and Forward must render their corresponding recorded page.
    function pop() {
      setPath(location.pathname+location.search+location.hash);
      setRevision((previous) => previous + 1);
    }
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  const navigate = useCallback((next: string, replace = false) => {
    if (replace) history.replaceState(null, "", next);
    else history.pushState(null, "", next);
    setPath(next);
    // Re-selecting the current menu item must refresh its navigation counts too.
    setRevision((previous) => previous + 1);
  }, []);
  return { path, navigate, revision };
}

// Preserve native open-in-new-tab behavior while handling ordinary same-app navigation locally.
export function followLink(
  event: MouseEvent<HTMLAnchorElement>,
  path: string,
  navigate: (path: string) => void,
) {
  if (
    event.button ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  )
    return;
  event.preventDefault();
  navigate(path);
}
