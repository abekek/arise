import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAgents, fetchSkills } from "@/lib/api";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface SkillRow {
  id: string;
  name: string;
  description: string;
  status: string;
  origin: string;
  success_rate: number;
  invocation_count: number;
  agent_name: string;
}

export default function AllSkillsPage() {
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const agents = await fetchAgents();
        const all: SkillRow[] = [];
        for (const agent of agents) {
          const agentSkills = await fetchSkills(agent.id);
          if (Array.isArray(agentSkills)) {
            for (const s of agentSkills) {
              all.push({ ...s, agent_name: agent.name });
            }
          }
        }
        setSkills(all);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Loading skills...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-zinc-800">
        <h1 className="text-xl font-semibold text-zinc-100">All Skills</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {skills.length} skill{skills.length !== 1 ? "s" : ""} across all agents
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-zinc-500">Name</TableHead>
              <TableHead className="text-zinc-500">Agent</TableHead>
              <TableHead className="text-zinc-500">Status</TableHead>
              <TableHead className="text-zinc-500">Success Rate</TableHead>
              <TableHead className="text-zinc-500">Invocations</TableHead>
              <TableHead className="text-zinc-500">Origin</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {skills.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-zinc-600 py-8">
                  No skills evolved yet
                </TableCell>
              </TableRow>
            ) : (
              skills.map(s => (
                <TableRow key={s.id} className="border-zinc-800 hover:bg-zinc-900/50">
                  <TableCell>
                    <Link
                      to={`/skills/${s.id}`}
                      className="font-mono text-sm text-emerald-400 hover:underline"
                    >
                      {s.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-zinc-400">{s.agent_name}</TableCell>
                  <TableCell>
                    <Badge className={
                      s.status === "active"
                        ? "bg-emerald-950 text-emerald-400 border-0"
                        : s.status === "testing"
                        ? "bg-amber-950 text-amber-400 border-0"
                        : "bg-zinc-800 text-zinc-400 border-0"
                    }>
                      {s.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-sm text-zinc-300">
                    {(s.success_rate * 100).toFixed(0)}%
                  </TableCell>
                  <TableCell className="font-mono text-sm text-zinc-400">
                    {s.invocation_count}
                  </TableCell>
                  <TableCell>
                    <Badge className="bg-zinc-800 text-zinc-400 border-0">{s.origin}</Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
