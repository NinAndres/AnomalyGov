import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** Runs `load` whenever its dependencies change; ignores responses that arrive after a newer request. */
export function useApi<T>(load: (() => Promise<T>) | null, deps: unknown[]): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(load !== null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (load === null) {
      setLoading(false);
      return;
    }
    let current = true;
    setLoading(true);
    setError(null);
    load()
      .then((result) => current && setData(result))
      .catch((e: unknown) => current && setError(e instanceof ApiError ? e : new ApiError(0, null)))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [...deps, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}
