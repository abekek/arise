const API = window.location.origin;

export async function fetchAgents() {
  return fetch(`${API}/api/agents`).then(r => r.json());
}

export async function createAgent(data: any) {
  return fetch(`${API}/api/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(r => r.json());
}

export async function fetchAgent(id: string) {
  return fetch(`${API}/api/agents/${id}`).then(r => r.json());
}

export async function deleteAgent(id: string) {
  return fetch(`${API}/api/agents/${id}`, { method: "DELETE" });
}

export async function runTask(agentId: string, task: string) {
  return fetch(`${API}/api/agents/${agentId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  }).then(r => r.json());
}

export async function fetchSkills(agentId: string) {
  return fetch(`${API}/api/agents/${agentId}/skills`).then(r => r.json());
}

export async function fetchSkill(skillId: string) {
  return fetch(`${API}/api/skills/${skillId}`).then(r => r.json());
}

export async function fetchTrajectories(agentId: string) {
  return fetch(`${API}/api/agents/${agentId}/trajectories`).then(r => r.json());
}

export async function fetchEvolutions(agentId: string) {
  return fetch(`${API}/api/agents/${agentId}/evolutions`).then(r => r.json());
}

export async function fetchSettings() {
  return fetch(`${API}/api/settings`).then(r => r.json());
}

export async function updateSettings(data: any) {
  return fetch(`${API}/api/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(r => r.json());
}

export function createLiveSocket(agentId: string): WebSocket {
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(`${wsProto}//${window.location.host}/ws/agents/${agentId}/live`);
}
