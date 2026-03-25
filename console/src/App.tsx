import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import AgentsPage from "@/pages/AgentsPage";
import AgentDetailPage from "@/pages/AgentDetailPage";
import SkillDetailPage from "@/pages/SkillDetailPage";
import SettingsPage from "@/pages/SettingsPage";
import AllSkillsPage from "@/pages/AllSkillsPage";
import EvolutionLogPage from "@/pages/EvolutionLogPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<AgentsPage />} />
            <Route path="/agents/:id" element={<AgentDetailPage />} />
            <Route path="/skills" element={<AllSkillsPage />} />
            <Route path="/skills/:id" element={<SkillDetailPage />} />
            <Route path="/evolutions" element={<EvolutionLogPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={
                <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
                  Page not found
                </div>
              }
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
