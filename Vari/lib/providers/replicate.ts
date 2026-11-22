export type ReplicatePayload = {
  _provider: "replicate";
  version?: string;
  model?: string;
  deployment?: {
    owner: string;
    name: string;
  };
  _repeat?: number;
  input: Record<string, unknown>;
};

const API = "https://api.replicate.com/v1/predictions";

function token(): string {
  const t = process.env.REPLICATE_API_TOKEN;
  if (!t) {
    throw new Error(
      "Chybí REPLICATE_API_TOKEN v prostředí. Engine na Replicate bez něj nepoběží.",
    );
  }
  return t;
}

export async function createReplicatePrediction(
  payload: ReplicatePayload,
  opts: { signal?: AbortSignal } = {},
): Promise<{ id: string; status: string }> {
  const endpoint = payload.deployment
    ? `https://api.replicate.com/v1/deployments/${payload.deployment.owner}/${payload.deployment.name}/predictions`
    : API;
  const body = payload.deployment
    ? { input: payload.input }
    : payload.model
      ? { model: payload.model, input: payload.input }
      : { version: payload.version, input: payload.input };
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { Authorization: `Token ${token()}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || data.error || "Replicate request failed.");
  }
  return { id: data.id, status: data.status };
}

export async function getReplicatePrediction(
  id: string,
  opts: { signal?: AbortSignal } = {},
) {
  const res = await fetch(`${API}/${id}`, {
    headers: { Authorization: `Token ${token()}` },
    signal: opts.signal,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || data.error || "Replicate status failed.");
  }
  return data as {
    id: string;
    status: string;
    output?: string[] | string | null;
    error?: string | null;
    logs?: string;
  };
}

export async function cancelReplicatePrediction(id: string): Promise<void> {
  await fetch(`${API}/${id}/cancel`, {
    method: "POST",
    headers: { Authorization: `Token ${token()}` },
  }).catch(() => undefined);
}
