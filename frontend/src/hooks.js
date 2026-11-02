import { useCallback, useEffect, useRef, useState } from "react";

export function useLoad(loader, deps = [], { skip = false } = {}) {
  const [state, setState] = useState({ data: null, loading: !skip, error: null });
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    if (skip) {
      setState({ data: null, loading: false, error: null });
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setState((current) => ({ ...current, loading: true, error: null }));
    Promise.resolve()
      .then(() => loaderRef.current(controller.signal))
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!active || error.name === "AbortError") return;
        setState({ data: null, loading: false, error: error.message || "Request failed." });
      });
    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, skip]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, reload, setData: (data) => setState((current) => ({ ...current, data })) };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn) => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  }, []);
  return [busy, run];
}
