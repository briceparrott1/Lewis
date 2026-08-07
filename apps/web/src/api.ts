const BASE = "/api";

async function handle(res: Response) {
  if (!res.ok) throw new Error(`${res.status}`);
  const ct = res.headers.get("content-type") ?? "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  get: (path: string) => fetch(BASE + path, { credentials: "include" }).then(handle),
  post: (path: string, body?: unknown) =>
    fetch(BASE + path, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(handle),
  put: (path: string, body: unknown) =>
    fetch(BASE + path, {
      method: "PUT",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(handle),
  del: (path: string) =>
    fetch(BASE + path, { method: "DELETE", credentials: "include" }).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`);
    }),
  uploadFile: (path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(BASE + path, {
      method: "POST",
      credentials: "include",
      body: fd,
    }).then(handle);
  },
};
