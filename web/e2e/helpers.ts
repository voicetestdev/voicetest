/**
 * Shared helpers for e2e tests.
 */

/**
 * Delete all agents whose names match a prefix via the REST API.
 * Looks up agents by name, then deletes each match.
 * Silently ignores errors so cleanup never causes test failures.
 */
export async function deleteAgentsByPrefix(
  baseURL: string,
  prefix: string,
): Promise<void> {
  try {
    const res = await fetch(`${baseURL}/api/agents`);
    if (!res.ok) return;
    const agents: { id: string; name: string }[] = await res.json();
    for (const agent of agents) {
      if (agent.name.startsWith(prefix)) {
        await fetch(`${baseURL}/api/agents/${agent.id}`, {
          method: "DELETE",
        }).catch(() => {});
      }
    }
  } catch {
    // Cleanup should never fail the test
  }
}
